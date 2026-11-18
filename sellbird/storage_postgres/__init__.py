"""Sellbird's Postgres 18 storage backend (psycopg 3).

A ``postgresql://`` connection string is a storage locator (sellbird.storage),
so ``StateManager(db_path=os.environ["SELLBIRD_DATABASE_URL"])`` runs every
store on Postgres with no other change. Install with ``pip install
'sellbird[postgres]'``.

Roles (docs/platform-interface.md, "Database provisioning"):

- The app connects as the runtime role (``sellbird_app``), which can read and
  write rows and nothing else. It never changes the schema: ``check_schema``
  only reads ``schema_version`` and refuses to run on any version but
  ``EXPECTED_SCHEMA_VERSION``.
- ``sellbird storage migrate`` connects as the migration role
  (``sellbird_migrate``), which owns the schema, and applies the versioned
  migrations in ``migrations/postgres`` (sellbird.storage_postgres.migrate).

Row-level security is deliberately not used: one Sellbird workspace per
database, isolated by database and role (ADR 0001).
"""

from __future__ import annotations

from sellbird import storage

# The schema version this code runs on: the number of the newest file in
# migrations/postgres. A test keeps the two equal.
EXPECTED_SCHEMA_VERSION = 5


def _dsn(name: str) -> str:
    """The connection string again: the locator ``postgresql://...`` was split
    at its first colon, so ``name`` is ``//user:password@host/db?...``."""
    if not name.startswith("//"):
        raise ValueError("a Postgres locator is a postgresql:// connection string")
    return "postgresql:" + name


class PostgresBackend:
    """The storage backend behind ``postgresql://`` and ``postgres://`` locators."""

    dialect = "postgres"

    def __init__(self) -> None:
        self._known: set[str] = set()

    async def connect(self, name: str, *, timeout: float):
        from sellbird.storage_postgres.connection import open_connection

        return await open_connection(_dsn(name), timeout=timeout)

    async def check_schema(self, name: str) -> None:
        """Fail closed unless the schema is exactly the version this code expects."""
        db = await self.connect(name, timeout=storage.BUSY_TIMEOUT_SECONDS)
        try:
            async with db.execute("SELECT MAX(version) FROM schema_version") as cur:
                row = await cur.fetchone()
        except storage.OperationalError as e:
            if "no such table" not in str(e):
                raise
            row = None
        finally:
            await db.close()
        version = row[0] if row else None
        if version is None:
            raise storage.SchemaVersionError(
                "The Postgres schema isn't there yet: run `sellbird storage migrate` "
                "with the migration role's connection string first.")
        if version < EXPECTED_SCHEMA_VERSION:
            raise storage.SchemaVersionError(
                f"The Postgres schema is at version {version}; this Sellbird needs "
                f"version {EXPECTED_SCHEMA_VERSION}. Run `sellbird storage migrate`.")
        if version > EXPECTED_SCHEMA_VERSION:
            raise storage.SchemaVersionError(
                f"The Postgres schema is at version {version}, newer than this "
                f"Sellbird (version {EXPECTED_SCHEMA_VERSION}). Run the Sellbird "
                "release that migrated it, or migrate down with the migration role.")
        self._known.add(name)

    def exists(self, name: str) -> bool:
        """Whether the database is reachable and has been migrated at least once."""
        if name in self._known:
            return True
        try:
            row = self.read_one(name, "SELECT 1 FROM schema_version LIMIT 1", ())
        except storage.ERRORS:
            return False
        if row is not None:
            self._known.add(name)
        return row is not None

    def read_one(self, name: str, sql: str, params: tuple) -> tuple | None:
        from sellbird.storage_postgres.connection import read_one_sync

        return read_one_sync(_dsn(name), sql, params, timeout=storage.BUSY_TIMEOUT_SECONDS)


__all__ = ["EXPECTED_SCHEMA_VERSION", "PostgresBackend"]
