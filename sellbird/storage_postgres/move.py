"""``sellbird storage move``: copy a SQLite sellbird.db into an empty Postgres database.

    sellbird storage move --from data/sellbird.db --to-env SELLBIRD_DATABASE_URL

What it guarantees:

- The source is opened read-only and read from one snapshot; it is never changed.
- The source must be on the newest SQLite schema (``PRAGMA user_version`` equal
  to the number of ``state.MIGRATIONS``) and the target exactly on
  ``EXPECTED_SCHEMA_VERSION``, with the same tables and columns on both sides.
  Anything else is refused before a row is written.
- Everything happens in ONE Postgres transaction. The tables are locked against
  writers, a target that already holds any Sellbird row is refused (nothing is
  written), every table is copied in foreign-key order (the governed signal
  vocabulary before the observations that name it) with its ids and SQLite
  ``rowid`` kept, then read back and compared with the source, row count and
  checksum, before the commit. Any difference rolls the whole move back.
- Values arrive as they were: timestamps and JSON are text and are copied
  byte for byte, numbers keep their type, NULLs stay NULL, and signal
  confirmation state is just the ``signal_codes.status`` text.
- Each hidden ``rowid`` identity is reset afterwards, so the next row Postgres
  inserts follows the moved ones.
- The connection string is read from the variable ``--to-env`` names and is
  never printed. Run it with the runtime role (``sellbird_app``): it needs only
  to read and write rows and advance the rowid sequences.

The checksum of a table (``Checksum``) is the SHA-256 of UTF-8 lines: first the
JSON array of its column names (``rowid`` included) in sorted order, then for
each row in ``rowid`` order the JSON array of that row's values in the same
column order (compact separators, non-ASCII kept as is, NULL as ``null``,
integers as integers, floats as Python's ``repr``). Both sides of the move are
hashed this way, so equal checksums mean equal contents, value types included.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

# Every Sellbird table, in foreign-key dependency order: a table comes after
# every table it references. Today the only reference is
# observations.signal_code -> signal_codes.code; the target's catalog is
# checked against this order before anything is copied.
TABLES: tuple[str, ...] = (
    "signal_codes",
    "companies",
    "prospects",
    "campaigns",
    "conversations",
    "observations",
    "runs",
    "outbox",
    "suppressions",
    "mailboxes",
    "campaign_mailboxes",
    "actions",
    "usage_log",
    "usage_events",
    "processed_replies",
    "email_patterns",
    "settings",
    "feedback",
)
ROWID = "rowid"
BATCH_ROWS = 1000
# A move is one long transaction; the runtime role's 30 s default would cut a
# large table's COPY short. Waiting for a lock is bounded separately, so a
# running Sellbird makes the move stop rather than hang.
STATEMENT_TIMEOUT = "15min"
LOCK_TIMEOUT = "10s"
CONNECT_TIMEOUT_SECONDS = 10
_POSTGRES_TYPES = ("text", "bigint", "double precision")


class MoveError(RuntimeError):
    """The move can't go ahead, or stopped; nothing was written to the target."""


class TargetNotEmpty(MoveError):
    """The target already holds Sellbird rows; nothing was written."""


@dataclass(frozen=True)
class TableResult:
    name: str
    rows: int
    checksum: str


@dataclass(frozen=True)
class MoveReport:
    tables: tuple[TableResult, ...]
    schema_version: int

    @property
    def total_rows(self) -> int:
        return sum(t.rows for t in self.tables)


# ── Checksums ──

def _line(values: Any) -> bytes:
    text = json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


class Checksum:
    """The checksum of one table's rows (see the module docstring)."""

    def __init__(self, columns: Sequence[str]):
        self._order = sorted(range(len(columns)), key=lambda i: columns[i])
        self._hash = hashlib.sha256(_line(sorted(columns)))
        self.rows = 0

    def add(self, row: Sequence[Any]) -> None:
        self._hash.update(_line(row[i] for i in self._order))
        self.rows += 1

    def hexdigest(self) -> str:
        return "sha256:" + self._hash.hexdigest()


# ── The SQLite source ──

def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _open_source(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise MoveError(f"There is no SQLite database at {path}.")
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, isolation_level=None)
    except sqlite3.Error:
        raise MoveError(f"{path} isn't a readable SQLite database.") from None
    try:
        conn.execute("BEGIN")  # one snapshot for every table read below
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except sqlite3.Error:
        conn.close()
        raise MoveError(f"{path} isn't a readable SQLite database.") from None
    return conn


def _source_layout(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Each table's columns, after checking the source is a current Sellbird database."""
    from sellbird.state import MIGRATIONS

    (version,) = conn.execute("PRAGMA user_version").fetchone()
    if version < len(MIGRATIONS):
        raise MoveError(
            f"The SQLite database is at schema version {version}; the move needs "
            f"{len(MIGRATIONS)}. Run any sellbird command with it once (for example "
            "`sellbird status`) to bring it up to date, then move it.")
    if version > len(MIGRATIONS):
        raise MoveError(
            f"The SQLite database is at schema version {version}, newer than this "
            f"Sellbird ({len(MIGRATIONS)}). Move it with the release that made it.")
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}
    unknown, missing = sorted(names - set(TABLES)), sorted(set(TABLES) - names)
    if unknown:
        raise MoveError(
            "The SQLite database has tables Sellbird doesn't know, which the move "
            f"would leave behind: {', '.join(unknown)}.")
    if missing:
        raise MoveError(f"The SQLite database is missing tables: {', '.join(missing)}.")
    return {t: [r[1] for r in conn.execute(f"PRAGMA table_info({_quote(t)})")] for t in TABLES}


def _source_rows(conn: sqlite3.Connection, table: str,
                 columns: Sequence[str]) -> Iterator[tuple]:
    """The table's rows, the given columns then rowid, in rowid order."""
    select = ", ".join(_quote(c) for c in columns)
    cur = conn.execute(f"SELECT {select}, rowid FROM {_quote(table)} ORDER BY rowid")
    while batch := cur.fetchmany(BATCH_ROWS):
        yield from batch


def sqlite_checksums(path: Path) -> tuple[TableResult, ...]:
    """Row count and checksum of every table in a SQLite Sellbird database, as stored.

    Needs no Postgres; for a database whose values already have their column's
    type these equal what ``move`` reports."""
    with closing(_open_source(Path(path))) as conn:
        layout = _source_layout(conn)
        results = []
        for table in TABLES:
            checksum = Checksum([*layout[table], ROWID])
            for row in _source_rows(conn, table, layout[table]):
                checksum.add(row)
            results.append(TableResult(table, checksum.rows, checksum.hexdigest()))
        return tuple(results)


# ── Values ──

def _coerce(value: Any, pg_type: str, where: str) -> Any:
    """A SQLite value as the target column's type, or refuse (SQLite's typing is loose)."""
    if value is None:
        return None
    if pg_type == "text":
        if isinstance(value, str):
            if "\x00" in value:
                raise MoveError(f"{where} holds a NUL character, which Postgres text can't store.")
            return value
        if isinstance(value, (int, float)):
            return str(value)
    elif pg_type == "bigint":
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                pass
    elif pg_type == "double precision":
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    raise MoveError(f"{where} holds a {type(value).__name__} value that can't become {pg_type}.")


# ── The Postgres target ──

def _target_version(conn: Any) -> int:
    from psycopg import errors as pg

    from sellbird.storage_postgres import EXPECTED_SCHEMA_VERSION

    try:
        (version,) = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    except pg.UndefinedTable:
        version = None
    if version != EXPECTED_SCHEMA_VERSION:
        found = "not migrated" if version is None else f"at schema version {version}"
        raise MoveError(
            f"The target database is {found}; the move needs version "
            f"{EXPECTED_SCHEMA_VERSION}. Run `sellbird storage migrate` with the "
            "migration role first.")
    return version


def _target_layout(conn: Any) -> dict[str, list[tuple[str, str]]]:
    """Each table's (column, type) pairs, rowid last, after checking tables and references."""
    rows = conn.execute(
        """SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attidentity
           FROM pg_attribute a
           JOIN pg_class c ON c.oid = a.attrelid
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
             AND c.relname <> 'schema_version' AND a.attnum > 0 AND NOT a.attisdropped
           ORDER BY c.relname, a.attnum""").fetchall()
    layout: dict[str, list[tuple[str, str]]] = {}
    identities: set[str] = set()
    for table, column, pg_type, identity in rows:
        if column == ROWID:
            if pg_type == "bigint" and identity == "d":
                identities.add(table)
            continue
        layout.setdefault(table, []).append((column, pg_type))
    unknown, missing = sorted(set(layout) - set(TABLES)), sorted(set(TABLES) - set(layout))
    if unknown or missing:
        raise MoveError(
            "The target's tables don't match this Sellbird's "
            f"(unknown: {', '.join(unknown) or 'none'}; missing: {', '.join(missing) or 'none'}).")
    lacking = sorted(set(TABLES) - identities)
    if lacking:
        raise MoveError(f"These target tables lack the rowid identity: {', '.join(lacking)}.")
    position = {t: i for i, t in enumerate(TABLES)}
    for child, parent in conn.execute(
            """SELECT cl.relname, cf.relname FROM pg_constraint k
               JOIN pg_class cl ON cl.oid = k.conrelid
               JOIN pg_class cf ON cf.oid = k.confrelid
               JOIN pg_namespace n ON n.oid = cl.relnamespace
               WHERE k.contype = 'f' AND n.nspname = 'public'""").fetchall():
        if position.get(parent, -1) >= position.get(child, -1):
            raise MoveError(f"{child} references {parent}, which the move copies later.")
    for table, columns in layout.items():
        odd = sorted({t for _, t in columns} - set(_POSTGRES_TYPES))
        if odd:
            raise MoveError(f"{table} has column types the move doesn't handle: {', '.join(odd)}.")
    return layout


def _check_columns(source: dict[str, list[str]], target: dict[str, list[tuple[str, str]]]) -> None:
    for table in TABLES:
        theirs, ours = set(source[table]), {c for c, _ in target[table]}
        if theirs != ours:
            raise MoveError(
                f"{table} has different columns in the two databases (only in SQLite: "
                f"{', '.join(sorted(theirs - ours)) or 'none'}; only in Postgres: "
                f"{', '.join(sorted(ours - theirs)) or 'none'}).")


def _lock_and_require_empty(conn: Any) -> None:
    from psycopg import sql

    names = sql.SQL(", ").join(sql.Identifier(t) for t in TABLES)
    conn.execute(sql.SQL("LOCK TABLE {} IN EXCLUSIVE MODE").format(names))
    occupied = [t for t in TABLES if conn.execute(
        sql.SQL("SELECT EXISTS (SELECT 1 FROM {})").format(sql.Identifier(t))).fetchone()[0]]
    if occupied:
        raise TargetNotEmpty(
            f"The target already holds Sellbird rows (in {', '.join(occupied)}), so "
            "nothing was written. Move only into a freshly migrated, empty database.")


def _copy_table(conn: Any, source: sqlite3.Connection, table: str,
                columns: list[tuple[str, str]]) -> TableResult:
    from psycopg import sql

    names = [c for c, _ in columns]
    types = [t for _, t in columns]
    checksum = Checksum([*names, ROWID])
    query = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(table), sql.SQL(", ").join(sql.Identifier(c) for c in [*names, ROWID]))
    with conn.cursor() as cur, cur.copy(query) as copy:
        for row in _source_rows(source, table, names):
            rowid = row[-1]
            values = tuple(
                _coerce(v, t, f"{table}.{c} (rowid {rowid})")
                for v, t, c in zip(row, types, names)) + (rowid,)
            checksum.add(values)
            copy.write_row(values)
    return TableResult(table, checksum.rows, checksum.hexdigest())


def _read_back(conn: Any, table: str, columns: list[tuple[str, str]]) -> TableResult:
    from psycopg import sql

    names = [c for c, _ in columns]
    checksum = Checksum([*names, ROWID])
    query = sql.SQL("SELECT {} FROM {} ORDER BY {}").format(
        sql.SQL(", ").join(sql.Identifier(c) for c in [*names, ROWID]),
        sql.Identifier(table), sql.Identifier(ROWID))
    with conn.cursor(name=f"sellbird_move_{table}") as cur:
        cur.itersize = BATCH_ROWS
        cur.execute(query)
        for row in cur:
            checksum.add(row)
    return TableResult(table, checksum.rows, checksum.hexdigest())


def _reset_identity(conn: Any, table: str) -> None:
    from psycopg import sql

    conn.execute(
        sql.SQL("SELECT setval(pg_get_serial_sequence(%s, %s), "
                "COALESCE((SELECT MAX({}) FROM {}), 0) + 1, false)").format(
            sql.Identifier(ROWID), sql.Identifier(table)),
        (f"public.{table}", ROWID))


def _run(conn: Any, source: sqlite3.Connection, layout: dict[str, list[str]]) -> MoveReport:
    with conn.transaction():
        conn.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
        conn.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
        version = _target_version(conn)
        target = _target_layout(conn)
        _check_columns(layout, target)
        _lock_and_require_empty(conn)
        copied = [_copy_table(conn, source, t, target[t]) for t in TABLES]
        for sent in copied:
            arrived = _read_back(conn, sent.name, target[sent.name])
            if arrived != sent:
                raise MoveError(
                    f"{sent.name} didn't arrive intact ({sent.rows} rows sent, "
                    f"{arrived.rows} read back, or their checksums differ); "
                    "nothing was written.")
        for table in TABLES:
            _reset_identity(conn, table)
    return MoveReport(tuple(copied), version)


def move(source_path: Path, dsn: str) -> MoveReport:
    """Copy the SQLite database at ``source_path`` into the empty Postgres at ``dsn``.

    All or nothing: raises ``MoveError`` (``TargetNotEmpty`` for a target with
    rows) and leaves the target as it was, or commits every table."""
    with closing(_open_source(Path(source_path))) as source:
        layout = _source_layout(source)
        try:
            import psycopg
            from psycopg import errors as pg_errors
        except ImportError:
            raise MoveError(
                "Postgres support isn't installed: pip install 'sellbird[postgres]'") from None

        from sellbird.storage_postgres.errors import translate_error

        try:
            conn = psycopg.connect(dsn, autocommit=True, application_name="sellbird-move",
                                   connect_timeout=CONNECT_TIMEOUT_SECONDS)
        except psycopg.Error:  # never echo psycopg's message: it can quote the DSN
            raise MoveError("Could not reach the Postgres database.") from None
        try:
            return _run(conn, source, layout)
        except pg_errors.LockNotAvailable:
            raise MoveError(
                "Something is using the target database (a running Sellbird?). Stop it "
                "and move again; nothing was written.") from None
        except psycopg.Error as e:
            raise MoveError(f"The move stopped and nothing was written: {translate_error(e)}") from None
        finally:
            conn.close()


# ── Command line ──

def format_report(report: MoveReport, source: Path, env_name: str) -> str:
    width = max(len(t) for t in TABLES)
    lines = [
        f"\n  Moved {source} into Postgres (using {env_name}, schema version "
        f"{report.schema_version}).\n",
        f"  {'table':<{width}}  {'rows':>8}  checksum",
    ]
    lines += [f"  {t.name:<{width}}  {t.rows:>8}  {t.checksum}" for t in report.tables]
    lines.append(f"  {'total':<{width}}  {report.total_rows:>8}\n")
    return "\n".join(lines)


def cmd_move(args: Any) -> None:
    source = (getattr(args, "from_path", "") or "").strip()
    env_name = (getattr(args, "to_env", "") or "").strip()
    if not source or not env_name:
        sys.exit("\n  Usage: sellbird storage move --from data/sellbird.db "
                 "--to-env SELLBIRD_DATABASE_URL\n")
    dsn = os.environ.get(env_name, "").strip()
    if not dsn:
        sys.exit(f"\n  Set {env_name} to the target database's connection string.\n")
    if not dsn.startswith(("postgresql://", "postgres://")):
        sys.exit(f"\n  {env_name} isn't a postgresql:// connection string.\n")
    try:
        report = move(Path(source), dsn)
    except MoveError as e:
        sys.exit(f"\n  {e}\n")
    print(format_report(report, Path(source), env_name))


__all__ = [
    "Checksum", "MoveError", "MoveReport", "TABLES", "TableResult", "TargetNotEmpty",
    "cmd_move", "format_report", "move", "sqlite_checksums",
]
