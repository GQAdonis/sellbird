"""Versioned, reversible Postgres migrations, applied with the migration role.

Files live in ``migrations/postgres`` (or ``$SELLBIRD_MIGRATIONS_DIR``) as
pairs ``NNNN_name.up.sql`` / ``NNNN_name.down.sql``, numbered 0001, 0002, ...
with no gaps. Each applied migration is a row in ``schema_version`` (version,
name, checksum of its up file, when). The schema's version is the highest row.

Rules the runner enforces:

- Only a role that may create objects in schema ``public`` can migrate. The
  runtime role can't, so pointing this at the app's connection string fails
  with a clear message instead of half-working.
- One migrator at a time (a session advisory lock).
- Each migration runs in its own transaction together with its
  ``schema_version`` row: it is applied completely or not at all.
- An applied migration whose file has since changed, or that this code
  doesn't know, stops the run: released migrations are never edited.
- Down migrations run only when asked for a target version (an operator
  action, never automatic).

``schema_version`` is created by the runner (owned by the migration role) and
only the migration role may change it; the runtime role keeps SELECT, to check
the version it runs on.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

MIGRATIONS_DIR_ENV = "SELLBIRD_MIGRATIONS_DIR"
# A fixed key for pg_advisory_lock: "Sell" in ASCII.
ADVISORY_LOCK_KEY = 0x53656C6C
_FILENAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.(up|down)\.sql$")

_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_version (
    version integer PRIMARY KEY CHECK (version > 0),
    name text NOT NULL,
    checksum text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE schema_version IS
    'Applied Sellbird migrations (migrations/postgres). Written only by sellbird storage migrate.';
DO $$
DECLARE
    r record;
BEGIN
    -- Default privileges hand every new table to the runtime role; this one is
    -- the migration role's alone to change.
    FOR r IN
        SELECT DISTINCT grantee FROM information_schema.role_table_grants
        WHERE table_schema = 'public' AND table_name = 'schema_version'
          AND grantee <> current_user
          AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')
    LOOP
        IF r.grantee = 'PUBLIC' THEN
            EXECUTE 'REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER '
                    'ON public.schema_version FROM PUBLIC';
        ELSE
            EXECUTE format('REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER '
                           'ON public.schema_version FROM %I', r.grantee);
        END IF;
    END LOOP;
END
$$;
"""


class MigrationError(RuntimeError):
    """The migrations can't be applied as asked; nothing further was changed."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    up: Path
    down: Path

    def up_sql(self) -> str:
        return self.up.read_text(encoding="utf-8")

    def down_sql(self) -> str:
        return self.down.read_text(encoding="utf-8")

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.up.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Status:
    current: int
    latest: int
    applied: tuple[int, ...]

    @property
    def pending(self) -> int:
        return max(0, self.latest - self.current)


def migrations_dir() -> Path:
    override = os.environ.get(MIGRATIONS_DIR_ENV, "").strip()
    if override:
        return Path(override)
    from sellbird.paths import PACKAGE_ROOT

    return PACKAGE_ROOT / "migrations" / "postgres"


def discover(directory: Path | None = None) -> list[Migration]:
    """Every migration, in order. Refuses gaps, strays and half pairs."""
    folder = Path(directory) if directory is not None else migrations_dir()
    if not folder.is_dir():
        raise MigrationError(f"no migrations folder at {folder}")
    found: dict[int, dict[str, tuple[str, Path]]] = {}
    for path in sorted(folder.glob("*.sql")):
        m = _FILENAME.match(path.name)
        if not m:
            raise MigrationError(f"{path.name} isn't named NNNN_name.up.sql or NNNN_name.down.sql")
        version, name, direction = int(m.group(1)), m.group(2), m.group(3)
        found.setdefault(version, {})[direction] = (name, path)
    migrations = []
    for expected, version in enumerate(sorted(found), start=1):
        if version != expected:
            raise MigrationError(f"migration {expected:04d} is missing (found {version:04d})")
        pair = found[version]
        if set(pair) != {"up", "down"}:
            raise MigrationError(f"migration {version:04d} needs both an up and a down file")
        (up_name, up), (down_name, down) = pair["up"], pair["down"]
        if up_name != down_name:
            raise MigrationError(f"migration {version:04d}'s up and down files disagree on its name")
        migrations.append(Migration(version, up_name, up, down))
    return migrations


# Seconds to wait for the server before giving up, so a migration Job against
# an unreachable database fails instead of hanging until it is killed.
CONNECT_TIMEOUT_SECONDS = 10


def _connect(dsn: str):
    import psycopg

    return psycopg.connect(dsn, autocommit=True, application_name="sellbird-migrate",
                           connect_timeout=CONNECT_TIMEOUT_SECONDS)


def _require_migration_role(conn) -> None:
    (allowed,) = conn.execute("SELECT has_schema_privilege('public', 'CREATE')").fetchone()
    if not allowed:
        raise MigrationError(
            "This role can't change the schema, so it can't run migrations. Use the "
            "migration role's connection string (SELLBIRD_MIGRATE_DATABASE_URL), "
            "never the app's.")


def _applied(conn) -> dict[int, str]:
    rows = conn.execute("SELECT version, checksum FROM schema_version ORDER BY version").fetchall()
    return {int(v): c for v, c in rows}


def _verify(applied: dict[int, str], migrations: list[Migration]) -> None:
    known = {m.version: m for m in migrations}
    for version, checksum in applied.items():
        m = known.get(version)
        if m is None:
            raise MigrationError(
                f"The database has migration {version:04d}, which this Sellbird doesn't "
                "have: it was migrated by a newer release.")
        if m.checksum != checksum:
            raise MigrationError(
                f"Migration {version:04d} ({m.name}) was changed after it was applied. "
                "Released migrations are never edited; add a new one instead.")


class _Session:
    """A migration-role connection holding the advisory lock."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.conn = None

    def __enter__(self):
        import psycopg

        try:
            self.conn = _connect(self.dsn)
        except psycopg.OperationalError:
            raise MigrationError("could not reach the Postgres database") from None
        except psycopg.Error as e:
            # The type only: never the server's text, which can echo the DSN.
            raise MigrationError(
                f"could not open the migration connection ({type(e).__name__})") from None
        try:
            _require_migration_role(self.conn)
            self.conn.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))
            self.conn.execute(_BOOTSTRAP)
        except BaseException:
            self.conn.close()
            raise
        return self.conn

    def __exit__(self, *exc: object) -> None:
        try:
            self.conn.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))
        finally:
            self.conn.close()


def status(dsn: str, directory: Path | None = None) -> Status:
    migrations = discover(directory)
    with _Session(dsn) as conn:
        applied = _applied(conn)
        _verify(applied, migrations)
    return Status(max(applied, default=0), len(migrations), tuple(sorted(applied)))


def migrate_up(dsn: str, target: int | None = None,
               directory: Path | None = None) -> list[Migration]:
    """Apply pending migrations up to ``target`` (default: the newest)."""
    migrations = discover(directory)
    latest = len(migrations)
    target = latest if target is None else target
    if not 0 <= target <= latest:
        raise MigrationError(f"there is no version {target}; the newest is {latest}")
    done: list[Migration] = []
    with _Session(dsn) as conn:
        applied = _applied(conn)
        _verify(applied, migrations)
        current = max(applied, default=0)
        if target < current:
            raise MigrationError(
                f"The schema is at version {current}, past {target}. Going back is "
                "`sellbird storage down --to` (an operator decision).")
        for m in migrations:
            if m.version in applied or m.version > target:
                continue
            with conn.transaction():
                conn.execute(m.up_sql())
                conn.execute(
                    "INSERT INTO schema_version (version, name, checksum) VALUES (%s, %s, %s)",
                    (m.version, m.name, m.checksum))
            done.append(m)
    return done


def migrate_down(dsn: str, target: int, directory: Path | None = None) -> list[Migration]:
    """Reverse applied migrations, newest first, until the schema is at ``target``."""
    migrations = discover(directory)
    if target < 0:
        raise MigrationError("the lowest version is 0 (no Sellbird tables)")
    by_version = {m.version: m for m in migrations}
    done: list[Migration] = []
    with _Session(dsn) as conn:
        applied = _applied(conn)
        _verify(applied, migrations)
        for version in sorted(applied, reverse=True):
            if version <= target:
                break
            m = by_version[version]
            with conn.transaction():
                conn.execute(m.down_sql())
                conn.execute("DELETE FROM schema_version WHERE version = %s", (version,))
            done.append(m)
    return done
