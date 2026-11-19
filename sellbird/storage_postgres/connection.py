"""An aiosqlite-shaped connection over psycopg 3, so the stores keep one code path.

Transactions behave as Python's sqlite3 module makes them behave:

- A statement that only reads runs on its own (autocommit), with no
  transaction left open behind it.
- The first statement that writes opens a transaction (READ COMMITTED), which
  lasts until ``commit()`` or ``rollback()``. Closing without either discards it.
- An explicit ``BEGIN`` opens a REPEATABLE READ transaction, the consistent
  snapshot a deferred SQLite transaction reads from.
- A statement that fails inside a transaction is undone on its own (a
  savepoint around it) and leaves the rest usable, as in SQLite, where Postgres
  would otherwise abort the whole transaction.

Results come back as tuples, or as ``Row`` objects (indexable by position and
by case-insensitive name, ``dict(row)`` works) when ``row_factory`` is set, as
the stores set it to ``aiosqlite.Row``. Values load as SQLite returns them:
integers and floats rather than Decimals, 1/0 rather than booleans.
"""

from __future__ import annotations

import datetime as _dt
import sqlite3
from typing import Any, Iterable, Sequence

import psycopg
from psycopg.adapt import Dumper, Loader

from sellbird import storage
from sellbird.storage_postgres.dialect import (
    first_word,
    is_read_only,
    keeps_rowid,
    translate,
)
from sellbird.storage_postgres.errors import translate_error

_TEXT_OID = 25
_INT8_OID = 20
_SAVEPOINT = "sellbird_statement"
_NO_OP_PRAGMAS = frozenset({"journal_mode", "synchronous", "foreign_keys", "busy_timeout"})


# ── Values in and out, as sqlite3 gives and takes them ──

class _NumericLoader(Loader):
    """numeric (what SUM over integers returns) as int, or float with a fraction."""

    def load(self, data: Any) -> int | float:
        text = bytes(data).decode()
        if any(c in text for c in ".eENI"):  # a fraction, an exponent, NaN, Infinity
            return float(text)
        return int(text)


class _BoolLoader(Loader):
    def load(self, data: Any) -> int:
        return 1 if bytes(data) == b"t" else 0


class _BoolDumper(Dumper):
    oid = _INT8_OID

    def dump(self, obj: bool) -> bytes:
        return b"1" if obj else b"0"


class _DateTimeDumper(Dumper):
    """As sqlite3's default adapter stores it: ISO text with a space."""

    oid = _TEXT_OID

    def dump(self, obj: _dt.datetime) -> bytes:
        return obj.isoformat(" ").encode()


class _DateDumper(Dumper):
    oid = _TEXT_OID

    def dump(self, obj: _dt.date) -> bytes:
        return obj.isoformat().encode()


def configure_adapters(adapters: Any) -> None:
    adapters.register_loader("numeric", _NumericLoader)
    adapters.register_loader("bool", _BoolLoader)
    adapters.register_dumper(bool, _BoolDumper)
    adapters.register_dumper(_dt.datetime, _DateTimeDumper)
    adapters.register_dumper(_dt.date, _DateDumper)


# ── Rows ──

class Row:
    """A result row like sqlite3.Row: by position, by name (any case), dict(row)."""

    __slots__ = ("_keys", "_index", "_values")

    def __init__(self, keys: tuple[str, ...], index: dict[str, int], values: tuple):
        self._keys = keys
        self._index = index
        self._values = values

    def keys(self) -> list[str]:
        return list(self._keys)

    def __getitem__(self, key: int | slice | str) -> Any:
        if isinstance(key, (int, slice)):
            return self._values[key]
        try:
            return self._values[self._index[key.lower()]]
        except KeyError:
            raise IndexError("No item with that key") from None

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, Row) and self._keys == other._keys
                and self._values == other._values)

    def __hash__(self) -> int:
        return hash((self._keys, self._values))

    def __repr__(self) -> str:
        return f"<Row {dict(zip(self._keys, self._values))!r}>"


class Cursor:
    """A finished statement's results, read eagerly (aiosqlite cursor shape)."""

    def __init__(self, description: tuple | None, rows: list, rowcount: int):
        self.description = description
        self.rowcount = rowcount
        self.lastrowid = None
        self._rows = rows
        self._at = 0

    async def fetchone(self) -> Any:
        if self._at >= len(self._rows):
            return None
        self._at += 1
        return self._rows[self._at - 1]

    async def fetchmany(self, size: int = 1) -> list:
        chunk = self._rows[self._at:self._at + size]
        self._at += len(chunk)
        return chunk

    async def fetchall(self) -> list:
        rest = self._rows[self._at:]
        self._at = len(self._rows)
        return rest

    def __aiter__(self):
        return self

    async def __anext__(self) -> Any:
        row = await self.fetchone()
        if row is None:
            raise StopAsyncIteration
        return row

    async def close(self) -> None:
        self._rows = []

    async def __aenter__(self) -> "Cursor":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


class _Pending:
    """What ``execute`` returns: await it for a cursor, or ``async with`` it."""

    def __init__(self, coro: Any):
        self._coro = coro
        self._cursor: Cursor | None = None

    def __await__(self):
        return self._coro.__await__()

    async def __aenter__(self) -> Cursor:
        self._cursor = await self._coro
        return self._cursor

    async def __aexit__(self, *exc: object) -> None:
        if self._cursor is not None:
            await self._cursor.close()


def shape_rows(sql: str, description: Sequence | None, raw: list, row_factory: Any,
               cursor_like: Any = None) -> tuple[tuple | None, list]:
    """sqlite3-shaped description and rows; hides ``rowid`` unless selected."""
    if description is None:
        return None, []
    names = [d.name for d in description]
    keep = [i for i, n in enumerate(names) if n != "rowid"] if not keeps_rowid(sql) else None
    if keep is not None and len(keep) != len(names):
        names = [names[i] for i in keep]
        raw = [tuple(r[i] for i in keep) for r in raw]
    shaped_description = tuple((n, None, None, None, None, None, None) for n in names)
    if row_factory is None:
        return shaped_description, [tuple(r) for r in raw]
    if row_factory is sqlite3.Row:
        keys = tuple(names)
        index: dict[str, int] = {}
        for i, n in enumerate(keys):
            index.setdefault(n.lower(), i)
        return shaped_description, [Row(keys, index, tuple(r)) for r in raw]
    holder = cursor_like if cursor_like is not None else Cursor(shaped_description, [], -1)
    return shaped_description, [row_factory(holder, tuple(r)) for r in raw]


class PgConnection:
    """One psycopg AsyncConnection (autocommit; transactions managed here)."""

    def __init__(self, conn: psycopg.AsyncConnection):
        self._conn = conn
        self._in_tx = False
        self.row_factory: Any = None

    @property
    def in_transaction(self) -> bool:
        return self._in_tx

    async def _raw(self, sql: str) -> None:
        await self._conn.execute(sql)

    async def _run(self, pg_sql: str, params: tuple, sql: str, many: Sequence | None = None) -> Cursor:
        async with self._conn.cursor() as cur:
            if many is not None:
                await cur.executemany(pg_sql, many)
            else:
                await cur.execute(pg_sql, params)
            raw = await cur.fetchall() if cur.description is not None else []
            rowcount = -1 if is_read_only(sql) else cur.rowcount
            description, rows = shape_rows(sql, cur.description, raw, self.row_factory)
        return Cursor(description, rows, rowcount)

    async def _guarded(self, sql: str, pg_sql: str, params: tuple,
                       many: Sequence | None = None) -> Cursor:
        """Run one statement with sqlite3's transaction rules (module docstring)."""
        try:
            if not self._in_tx and is_read_only(sql) and many is None:
                return await self._run(pg_sql, params, sql)
            began = not self._in_tx
            if began:
                await self._raw("BEGIN")
                self._in_tx = True
            else:
                await self._raw(f"SAVEPOINT {_SAVEPOINT}")
            try:
                cursor = await self._run(pg_sql, params, sql, many)
            except psycopg.Error:
                if began:
                    await self._raw("ROLLBACK")
                    self._in_tx = False
                else:
                    await self._raw(f"ROLLBACK TO SAVEPOINT {_SAVEPOINT}")
                    await self._raw(f"RELEASE SAVEPOINT {_SAVEPOINT}")
                raise
            if not began:
                await self._raw(f"RELEASE SAVEPOINT {_SAVEPOINT}")
            return cursor
        except psycopg.Error as e:
            raise translate_error(e) from None

    async def _statement(self, sql: str, params: Iterable | None) -> Cursor:
        word = first_word(sql)
        if word == "PRAGMA":
            return await self._pragma(sql)
        if word == "BEGIN":
            if self._in_tx:
                raise storage.OperationalError(
                    "cannot start a transaction within a transaction")
            await self._control("BEGIN ISOLATION LEVEL REPEATABLE READ")
            self._in_tx = True
            return Cursor(None, [], -1)
        if word in ("COMMIT", "END"):
            await self.commit()
            return Cursor(None, [], -1)
        if word == "ROLLBACK" and " TO " not in f" {sql.upper()} ":
            await self.rollback()
            return Cursor(None, [], -1)
        if isinstance(params, dict):
            raise storage.OperationalError("named parameters are not supported; use ?")
        args = tuple(params) if params is not None else ()
        return await self._guarded(sql, translate(sql, parametrized=True), args)

    async def _control(self, sql: str) -> None:
        try:
            await self._raw(sql)
        except psycopg.Error as e:
            raise translate_error(e) from None

    async def _pragma(self, sql: str) -> Cursor:
        body = sql.strip().rstrip(";")[len("PRAGMA"):].strip()
        name, _, value = body.partition("=")
        name = name.strip().lower()
        if name in _NO_OP_PRAGMAS:
            return Cursor(None, [], -1)
        if name == "user_version" and not value.strip():
            cursor = await self._guarded(
                "SELECT COALESCE(MAX(version), 0) FROM schema_version",
                "SELECT COALESCE(MAX(version), 0) FROM schema_version", ())
            return cursor
        raise storage.OperationalError(
            f"PRAGMA {name} has no meaning on Postgres; the schema is changed "
            "only by `sellbird storage migrate`")

    def execute(self, sql: str, params: Iterable | None = None) -> _Pending:
        return _Pending(self._statement(sql, params))

    def executemany(self, sql: str, seq_of_params: Iterable[Iterable]) -> _Pending:
        async def run() -> Cursor:
            rows = [tuple(p) for p in seq_of_params]
            if not rows:
                return Cursor(None, [], 0)
            return await self._guarded(sql, translate(sql, parametrized=True), (), many=rows)
        return _Pending(run())

    async def executescript(self, script: str) -> Cursor:
        """Commit what's pending (as sqlite3 does), then run the script."""
        await self.commit()
        pg_sql = translate(script, parametrized=False)
        try:
            await self._conn.execute(pg_sql)
        except psycopg.Error as e:
            raise translate_error(e) from None
        return Cursor(None, [], -1)

    async def commit(self) -> None:
        if self._in_tx:
            await self._control("COMMIT")
            self._in_tx = False

    async def rollback(self) -> None:
        if self._in_tx:
            await self._control("ROLLBACK")
            self._in_tx = False

    async def close(self) -> None:
        try:
            if self._in_tx:
                await self._raw("ROLLBACK")
        except psycopg.Error:
            pass  # the connection is going away either way
        finally:
            self._in_tx = False
            await self._conn.close()


async def open_connection(dsn: str, *, timeout: float) -> PgConnection:
    """Connect (autocommit; transactions are managed by PgConnection)."""
    try:
        conn = await psycopg.AsyncConnection.connect(
            dsn, autocommit=True, connect_timeout=max(1, int(timeout)))
    except psycopg.Error as e:
        raise translate_error(e) from None
    configure_adapters(conn.adapters)
    return PgConnection(conn)


def read_one_sync(dsn: str, sql: str, params: tuple, *, timeout: float) -> tuple | None:
    """One row of a read-only query on a short-lived synchronous connection."""
    if not is_read_only(sql):
        raise storage.OperationalError("read_one only runs queries that read")
    try:
        with psycopg.connect(dsn, autocommit=True,
                             connect_timeout=max(1, int(timeout))) as conn:
            configure_adapters(conn.adapters)
            with conn.cursor() as cur:
                cur.execute(translate(sql, parametrized=True), tuple(params))
                if cur.description is None:
                    return None
                raw = cur.fetchmany(1)
                _, rows = shape_rows(sql, cur.description, raw, None)
                return rows[0] if rows else None
    except psycopg.Error as e:
        raise translate_error(e) from None
