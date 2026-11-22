"""Postgres failures surface as failures, and their messages carry no values.

Needs the test DSNs (tests/storage_contract/backends.py); skips, saying why,
without them.
"""

from urllib.parse import quote, urlsplit, urlunsplit

import pytest

from sellbird import storage
from sellbird.storage_postgres import PostgresBackend
from tests.storage_contract.backends import migrate_to_latest, require_pg

# A value Postgres would quote back in its own error text.
PLANTED = "planted-value@example.com"


def _name(dsn: str) -> str:
    """The backend's name for a DSN: the locator split at its first colon."""
    return dsn.split(":", 1)[1]


def _closed_port(dsn: str) -> str:
    """The same DSN pointed at a local port nothing listens on."""
    parts = urlsplit(dsn)
    userinfo = parts.netloc.rpartition("@")[0]
    netloc = (userinfo + "@" if userinfo else "") + "127.0.0.1:1"
    return urlunsplit(parts._replace(netloc=netloc))


def test_an_unexpected_postgres_error_never_echoes_the_value():
    migrate_dsn, app_dsn = require_pg()
    migrate_to_latest(migrate_dsn)
    with pytest.raises(storage.ERRORS) as raised:
        storage.read_one(app_dsn, "SELECT CAST(? AS INTEGER)", (PLANTED,))
    assert PLANTED not in str(raised.value)
    assert getattr(raised.value, "sqlstate", None) == "22P02"


def test_exists_is_true_for_a_migrated_database():
    migrate_dsn, app_dsn = require_pg()
    migrate_to_latest(migrate_dsn)
    assert PostgresBackend().exists(_name(app_dsn))


def test_exists_raises_when_the_server_cannot_be_reached():
    _, app_dsn = require_pg()
    with pytest.raises(storage.ERRORS, match="could not reach"):
        PostgresBackend().exists(_name(_closed_port(app_dsn)))


# ── exists(): False only for sqlstate 3D000 or 42P01, never by message text ──
#
# How the connect-time cases were determined (by reading, not running): in
# psycopg 3.3.9, psycopg/generators.py `_connect` raises
# `OperationalError(f"connection failed: {libpq message}", pgconn=...)` with no
# `info` argument, and `psycopg.errors.Error.__init__` only fills `sqlstate`
# from `info`; `OperationalError.sqlstate` is None at class level. libpq hands
# a failed connection's error over as message text only (there is no result
# to read SQLSTATE fields from), so a FATAL 3D000 "database does not exist" or
# 28P01 "password authentication failed" arrives with `sqlstate` None.
# `translate_error` (sellbird/storage_postgres/errors.py) copies whatever
# sqlstate psycopg gives, so it drops nothing; the storage error is
# "could not reach the Postgres database" with `sqlstate` None, and exists()
# raises it.

MISSING_DATABASE = "sellbird_planted_missing_db"
WRONG_PASSWORD = "planted-wrong-password"


def _with_path(dsn: str, database: str) -> str:
    """The same DSN naming another database."""
    return urlunsplit(urlsplit(dsn)._replace(path="/" + database))


def _with_password(dsn: str, password: str) -> str:
    """The same DSN with another password for the same user."""
    parts = urlsplit(dsn)
    user = parts.username or ""
    host = parts.netloc.rpartition("@")[2]
    return urlunsplit(parts._replace(netloc=f"{user}:{quote(password, safe='')}@{host}"))


def _with_options(dsn: str, options: str) -> str:
    """The same DSN with libpq ``options`` (server settings for the session)."""
    parts = urlsplit(dsn)
    extra = "options=" + quote(options, safe="")
    query = f"{parts.query}&{extra}" if parts.query else extra
    return urlunsplit(parts._replace(query=query))


def test_exists_raises_for_a_missing_database_reported_at_connect():
    _, app_dsn = require_pg()
    with pytest.raises(storage.ERRORS) as raised:
        PostgresBackend().exists(_name(_with_path(app_dsn, MISSING_DATABASE)))
    # psycopg gives no sqlstate for a connect-time failure (see above), so this
    # is an unclassified connect failure: an outage, not an empty install. (If
    # pg_hba.conf names databases, the server refuses with 28000 instead; that
    # also arrives without a sqlstate and raises the same way.)
    assert getattr(raised.value, "sqlstate", None) is None
    assert MISSING_DATABASE not in str(raised.value)


def test_exists_raises_for_a_refused_password():
    _, app_dsn = require_pg()
    with pytest.raises(storage.ERRORS) as raised:
        PostgresBackend().exists(_name(_with_password(app_dsn, WRONG_PASSWORD)))
    assert getattr(raised.value, "sqlstate", None) is None
    assert WRONG_PASSWORD not in str(raised.value)


def test_exists_is_false_when_schema_version_is_not_there():
    migrate_dsn, app_dsn = require_pg()
    migrate_to_latest(migrate_dsn)
    # With only pg_catalog on the search path, the unqualified schema_version
    # isn't found: Postgres answers 42P01 (undefined_table) on a real query.
    hidden = _with_options(app_dsn, "-c search_path=pg_catalog")
    assert PostgresBackend().exists(_name(hidden)) is False


def test_exists_raises_for_a_refused_grant():
    import psycopg
    from psycopg import sql

    migrate_dsn, app_dsn = require_pg()
    migrate_to_latest(migrate_dsn)
    with psycopg.connect(app_dsn, autocommit=True) as conn:
        app_role = conn.execute("SELECT current_user").fetchone()[0]
    grant = sql.Identifier(app_role)
    with psycopg.connect(migrate_dsn, autocommit=True) as owner:
        owner.execute(sql.SQL("REVOKE SELECT ON schema_version FROM {}").format(grant))
        try:
            with pytest.raises(storage.ERRORS) as raised:
                PostgresBackend().exists(_name(app_dsn))
        finally:
            owner.execute(sql.SQL("GRANT SELECT ON schema_version TO {}").format(grant))
    assert getattr(raised.value, "sqlstate", None) == "42501"


# The classification itself, without a server: what read_one raises decides.

def _backend_raising(error: BaseException) -> PostgresBackend:
    backend = PostgresBackend()

    def read_one(name: str, sql: str, params: tuple) -> None:
        raise error

    backend.read_one = read_one  # type: ignore[method-assign]
    return backend


def _storage_error(message: str, sqlstate: str | None) -> storage.OperationalError:
    error = storage.OperationalError(message)
    error.sqlstate = sqlstate
    return error


@pytest.mark.parametrize("sqlstate", ["3D000", "42P01"])
def test_exists_is_false_only_for_the_not_there_sqlstates(sqlstate):
    backend = _backend_raising(_storage_error("not there", sqlstate))
    assert backend.exists("//nobody@db.example.com/sellbird") is False


@pytest.mark.parametrize("sqlstate", ["28P01", "42501", "42703", "57P03"])
def test_exists_raises_for_any_other_sqlstate(sqlstate):
    backend = _backend_raising(_storage_error("refused", sqlstate))
    with pytest.raises(storage.ERRORS):
        backend.exists("//nobody@db.example.com/sellbird")


def test_exists_never_reads_the_message_of_an_error_without_a_sqlstate():
    # Text that says "does not exist" is still an unclassified failure.
    error = _storage_error('database "sellbird" does not exist', None)
    with pytest.raises(storage.ERRORS):
        _backend_raising(error).exists("//nobody@db.example.com/sellbird")
