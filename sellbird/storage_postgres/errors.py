"""psycopg errors as storage errors, with SQLite-shaped messages.

The stores (and their tests) read constraint messages the way SQLite writes
them, for example ``"UNIQUE constraint failed: mailboxes.address"``. Postgres
says the same thing differently and includes the offending value in its
detail. These messages keep SQLite's shape and leave values out, so an email
address in a duplicate key never reaches a log line.
"""

from __future__ import annotations

import re

import psycopg
from psycopg import errors as pg

from sellbird import storage

# The governed vocabulary's foreign key (migration 0003) and the message
# SQLite's trigger raised, so both backends refuse an unknown code alike.
SIGNAL_CODE_FK = "observations_signal_code_fkey"
UNKNOWN_SIGNAL_MESSAGE = "unknown signal_code: not in signal_codes vocabulary"

_KEY_COLUMNS = re.compile(r"Key \(([^)]*)\)")


def _columns(detail: str | None) -> list[str]:
    m = _KEY_COLUMNS.search(detail or "")
    return [c.strip().strip('"') for c in m.group(1).split(",")] if m else []


def _integrity_message(exc: psycopg.Error) -> str:
    diag = exc.diag
    table = diag.table_name or ""
    if isinstance(exc, pg.UniqueViolation):
        cols = _columns(diag.message_detail)
        named = ", ".join(f"{table}.{c}" for c in cols) if cols else table
        return f"UNIQUE constraint failed: {named}".rstrip(": ")
    if isinstance(exc, pg.ForeignKeyViolation):
        if diag.constraint_name == SIGNAL_CODE_FK:
            return UNKNOWN_SIGNAL_MESSAGE
        return "FOREIGN KEY constraint failed"
    if isinstance(exc, pg.NotNullViolation):
        return f"NOT NULL constraint failed: {table}.{diag.column_name or ''}"
    if isinstance(exc, pg.CheckViolation):
        return f"CHECK constraint failed: {diag.constraint_name or table}"
    return "constraint failed"


def _undefined_message(exc: psycopg.Error) -> str:
    primary = exc.diag.message_primary or ""
    name = re.search(r'"([^"]+)"', primary)
    thing = name.group(1) if name else ""
    kind = "table" if isinstance(exc, pg.UndefinedTable) else "column"
    return f"no such {kind}: {thing}"


def translate_error(exc: psycopg.Error) -> storage.DatabaseError:
    """The storage error to raise for a psycopg one (never echoes values or DSNs).

    Raise it ``from None``: psycopg's own message carries the offending values.
    The SQLSTATE stays available as ``.sqlstate`` for diagnosis."""
    err = _translate(exc)
    err.sqlstate = getattr(exc, "sqlstate", None)
    return err


def _translate(exc: psycopg.Error) -> storage.DatabaseError:
    if isinstance(exc, psycopg.IntegrityError):
        return storage.IntegrityError(_integrity_message(exc))
    if isinstance(exc, (pg.UndefinedTable, pg.UndefinedColumn)):
        return storage.OperationalError(_undefined_message(exc))
    if isinstance(exc, pg.InsufficientPrivilege):
        return storage.PermissionDenied(
            f"permission denied: {exc.diag.message_primary or 'not allowed for this role'}")
    if isinstance(exc, pg.QueryCanceled):
        return storage.OperationalError("interrupted: the statement took too long")
    if isinstance(exc, psycopg.OperationalError):
        # Connection failures: say so without the connection string.
        return storage.OperationalError("could not reach the Postgres database")
    return storage.DatabaseError(exc.diag.message_primary or type(exc).__name__)
