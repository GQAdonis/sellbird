"""Where Sellbird's database is, and how to open it.

A database is named by a locator: a SQLite file path (the default, and all a
self-hosted install ever uses), ``:memory:``, or ``<prefix>:<name>`` for a
storage backend registered by an extension, such as a server keeping each
workspace in a shared database.

A backend is registered under its prefix, either in code with
``register_backend`` or through the ``sellbird.storage`` entry point group (the
entry point's name is the prefix, its value a zero-argument callable, such as
a class, returning the backend). Entry points load on first use, so a plain install
pays nothing.

Postgres is built in: a ``postgresql://`` or ``postgres://`` connection string
is itself a locator, served by ``sellbird.storage_postgres`` (psycopg 3,
installed with the ``postgres`` extra). Nothing Postgres is imported until such
a locator is used.

The connection contract every backend keeps:

- ``connect`` hands back a connection shaped like aiosqlite's (``execute``,
  ``executemany``, ``executescript``, ``commit``, ``rollback``, ``close``,
  ``row_factory``) that takes SQLite-dialect SQL with ``?`` placeholders, so
  the stores keep one code path. A write opens a transaction that lasts until
  ``commit`` or ``rollback``; closing without either discards it. A failed
  statement leaves the rest of its transaction usable, as in SQLite.
- Errors are raised as the classes below. Each subclasses the matching sqlite3
  class, so one ``except sqlite3.IntegrityError`` (or ``except
  INTEGRITY_ERRORS``) catches a constraint failure from any backend, and
  messages keep SQLite's shape ("UNIQUE constraint failed: table.column")
  without echoing the offending values.
- A backend that manages its own schema says so: ``StateManager.init_db`` then
  asks it to check the schema (``check_schema``, which never migrates and fails
  closed) instead of running the SQLite migrations.
- ``dialect`` (optional, default "sqlite") names the SQL dialect behind it, for
  the few queries that cannot be written once for both.
- ``read_one`` (optional) answers one read-only query synchronously, for code
  that cannot await (``storage.read_one``).
"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager, closing
from importlib import import_module
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, AsyncIterator, Protocol, runtime_checkable

BUSY_TIMEOUT_SECONDS = 30.0
ENTRY_POINT_GROUP = "sellbird.storage"


class DatabaseError(sqlite3.DatabaseError):
    """Any database failure in a backend other than SQLite."""


class IntegrityError(DatabaseError, sqlite3.IntegrityError):
    """A constraint failed in a backend other than SQLite. Subclasses sqlite3's,
    so the stores' ``except sqlite3.IntegrityError`` handlers keep working."""


class OperationalError(DatabaseError, sqlite3.OperationalError):
    """The database couldn't run the statement: unreachable, a missing table or
    column, a timeout. Subclasses sqlite3's, as SQLite raises these too."""


class PermissionDenied(OperationalError):
    """The connected role may not do this (for example DDL as the runtime role)."""


class SchemaVersionError(DatabaseError):
    """The schema is missing or not the version this code expects. Raised by
    ``check_schema``; the app refuses to start rather than run on it."""


# Catch these to handle any backend's failures, SQLite's included.
ERRORS: tuple[type[BaseException], ...] = (sqlite3.Error,)
INTEGRITY_ERRORS: tuple[type[BaseException], ...] = (sqlite3.IntegrityError,)

# Locator prefixes served by a backend that ships with Sellbird, imported on
# first use: a Postgres connection string is its own locator.
_BUILTIN_BACKENDS = {
    "postgresql": "sellbird.storage_postgres:PostgresBackend",
    "postgres": "sellbird.storage_postgres:PostgresBackend",
}


@runtime_checkable
class StorageBackend(Protocol):
    async def connect(self, name: str, *, timeout: float) -> Any:
        """An open, aiosqlite-shaped connection to the database called ``name``."""

    async def check_schema(self, name: str) -> None:
        """Raise if the schema is missing or behind. Never migrates."""

    def exists(self, name: str) -> bool:
        """Whether the database is there."""


_BACKENDS: dict[str, StorageBackend] = {}
_ENTRY_POINTS_LOADED = False


def register_backend(prefix: str, backend: StorageBackend) -> None:
    """Route locators ``<prefix>:<name>`` to ``backend``. Re-registering replaces."""
    if not prefix or not prefix.isidentifier():
        raise ValueError("a storage prefix is a short name like 'pg'")
    if not isinstance(backend, StorageBackend):
        raise TypeError("a storage backend needs connect, check_schema and exists")
    _BACKENDS[prefix] = backend


def unregister_backend(prefix: str) -> None:
    _BACKENDS.pop(prefix, None)


def _load_entry_points() -> None:
    global _ENTRY_POINTS_LOADED
    if _ENTRY_POINTS_LOADED:
        return
    _ENTRY_POINTS_LOADED = True
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        if ep.name in _BACKENDS:
            continue
        register_backend(ep.name, ep.load()())


def _load_builtin(prefix: str) -> None:
    """Register a built-in backend the first time its prefix is used."""
    target = _BUILTIN_BACKENDS.get(prefix)
    if target is None or prefix in _BACKENDS:
        return
    module_name, _, attr = target.partition(":")
    register_backend(prefix, getattr(import_module(module_name), attr)())


def split(locator) -> tuple[StorageBackend | None, str]:
    """The backend a locator names (None for SQLite) and the name it gives it."""
    text = str(locator)
    prefix, sep, rest = text.partition(":")
    if not sep or text == ":memory:" or not prefix.isidentifier() or len(prefix) == 1:
        # A path, :memory:, or a Windows drive letter (C:\\...).
        return None, text
    _load_entry_points()
    _load_builtin(prefix)
    backend = _BACKENDS.get(prefix)
    if backend is None:
        raise LookupError(f"no storage backend is registered for '{prefix}:'")
    return backend, rest


def dialect(locator) -> str:
    """The SQL dialect behind a locator: "sqlite", or what its backend says."""
    backend, _ = split(locator)
    return "sqlite" if backend is None else getattr(backend, "dialect", "sqlite")


def manages_schema(locator) -> bool:
    """True when a backend, not the SQLite migrations, owns this database's schema."""
    return split(locator)[0] is not None


@asynccontextmanager
async def connect(locator, *, timeout: float = BUSY_TIMEOUT_SECONDS) -> AsyncIterator[Any]:
    """Open the database a locator names, and close it after."""
    backend, name = split(locator)
    if backend is None:
        import aiosqlite

        db = await aiosqlite.connect(name, timeout=timeout)
    else:
        db = await backend.connect(name, timeout=timeout)
    try:
        yield db
    finally:
        await db.close()


async def check_schema(locator) -> None:
    backend, name = split(locator)
    if backend is not None:
        await backend.check_schema(name)


def exists(locator) -> bool:
    """Whether the database is there: the file for SQLite, the backend's answer otherwise."""
    backend, name = split(locator)
    return Path(name).exists() if backend is None else backend.exists(name)


def read_one(locator, sql: str, params: tuple = ()) -> tuple | None:
    """One row of a read-only query, synchronously, or None when there is none.

    For code that cannot await. SQLite opens the file read-only, so a missing
    file reads as no row and is never created; a backend answers through its
    own ``read_one``. Failures raise as ``ERRORS``.
    """
    backend, name = split(locator)
    if backend is None:
        if name == ":memory:" or not Path(name).exists():
            return None
        uri = Path(name).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT_SECONDS)) as db:
            return db.execute(sql, tuple(params)).fetchone()
    reader = getattr(backend, "read_one", None)
    if reader is None:
        raise OperationalError("this storage backend has no synchronous reads")
    return reader(name, sql, tuple(params))
