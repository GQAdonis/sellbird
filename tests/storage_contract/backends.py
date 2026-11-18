"""Run a test on every storage backend: SQLite always, Postgres when configured.

Postgres needs two connection strings to a throwaway database provisioned with
infra/postgres/provision.sql (the tests drop and recreate Sellbird's schema
there):

- SELLBIRD_TEST_PG_MIGRATE_DSN: the migration role (applies migrations,
  empties tables between tests).
- SELLBIRD_TEST_PG_APP_DSN: the runtime role (runs every case, as the app does).

Without both, every Postgres case is skipped with SKIP_REASON. Import the
fixtures into a test module with
``from tests.storage_contract.backends import locator, state  # noqa: F401``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import pytest_asyncio

from sellbird.state import StateManager

MIGRATE_ENV = "SELLBIRD_TEST_PG_MIGRATE_DSN"
APP_ENV = "SELLBIRD_TEST_PG_APP_DSN"
SKIP_REASON = (
    f"Postgres storage cases need {MIGRATE_ENV} and {APP_ENV}: connection strings "
    "for the migration and runtime roles of a throwaway Postgres 18 database "
    "provisioned with infra/postgres/provision.sql"
)
BACKENDS = ("sqlite", "postgres")


def pg_dsns() -> tuple[str, str] | None:
    migrate_dsn = os.environ.get(MIGRATE_ENV, "").strip()
    app_dsn = os.environ.get(APP_ENV, "").strip()
    return (migrate_dsn, app_dsn) if migrate_dsn and app_dsn else None


def require_pg() -> tuple[str, str]:
    """(migration DSN, runtime DSN), or skip this test saying what's missing."""
    dsns = pg_dsns()
    if dsns is None:
        pytest.skip(SKIP_REASON)
    return dsns


def migrate_to_latest(migrate_dsn: str) -> None:
    from sellbird.storage_postgres import migrate

    migrate.migrate_up(migrate_dsn)


def empty_tables(migrate_dsn: str) -> None:
    """Every Sellbird table emptied (the migration role owns them); schema kept."""
    import psycopg
    from psycopg import sql

    with psycopg.connect(migrate_dsn, autocommit=True) as conn:
        names = [r[0] for r in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename <> 'schema_version' ORDER BY tablename").fetchall()]
        if names:
            conn.execute(sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(
                sql.SQL(", ").join(sql.Identifier(n) for n in names)))


def fresh_pg_locator() -> str:
    """The runtime role's DSN, on the newest schema with every table empty."""
    migrate_dsn, app_dsn = require_pg()
    migrate_to_latest(migrate_dsn)
    empty_tables(migrate_dsn)
    return app_dsn


def fresh_locator(backend: str, folder: Path) -> str:
    if backend == "sqlite":
        return str(folder / "contract.db")
    return fresh_pg_locator()


@pytest.fixture(params=BACKENDS)
def locator(request, tmp_path) -> str:
    """A fresh, empty database on each backend, as a storage locator."""
    return fresh_locator(request.param, tmp_path)


@pytest_asyncio.fixture
async def state(locator) -> StateManager:
    """A StateManager on that database, ready (init_db: migrate SQLite, check Postgres)."""
    manager = StateManager(db_path=locator)
    await manager.init_db()
    return manager
