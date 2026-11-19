"""Postgres failures surface as failures, and their messages carry no values.

Needs the test DSNs (tests/storage_contract/backends.py); skips, saying why,
without them.
"""

from urllib.parse import urlsplit, urlunsplit

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
