"""Postgres migrations are versioned, reversible and applied only by the migration role.

The file checks run everywhere. The database checks need the test DSNs (see
tests/storage_contract/backends.py) and skip, saying why, without them; with
them they must all run, pg_dump included.
"""

import os
import re
import shutil
import subprocess

import pytest

from sellbird import storage
from sellbird.state import StateManager
from sellbird.storage_postgres import EXPECTED_SCHEMA_VERSION
from sellbird.storage_postgres import migrate as runner
from tests.storage_contract.backends import require_pg

PG_DUMP_ENV = "SELLBIRD_TEST_PG_DUMP"


# ── The files themselves ──

def test_migrations_are_complete_numbered_pairs_up_to_the_expected_version():
    migrations = runner.discover()
    assert [m.version for m in migrations] == list(range(1, EXPECTED_SCHEMA_VERSION + 1))
    for m in migrations:
        assert m.up_sql().strip() and m.down_sql().strip(), m.name


def test_migrations_never_create_roles_extensions_or_grants():
    for m in runner.discover():
        text = (m.up_sql() + m.down_sql()).lower()
        for forbidden in ("create role", "create extension", "grant ", "alter default privileges",
                          "security definer", "bypassrls", "create policy"):
            assert forbidden not in text, f"{m.up.name}: {forbidden}"


def _write(folder, name, sql="SELECT 1;"):
    (folder / name).write_text(sql)


def test_discover_refuses_a_gap(tmp_path):
    for name in ("0001_a.up.sql", "0001_a.down.sql", "0003_c.up.sql", "0003_c.down.sql"):
        _write(tmp_path, name)
    with pytest.raises(runner.MigrationError, match="0002 is missing"):
        runner.discover(tmp_path)


def test_discover_refuses_a_migration_without_its_down(tmp_path):
    _write(tmp_path, "0001_a.up.sql")
    with pytest.raises(runner.MigrationError, match="both an up and a down"):
        runner.discover(tmp_path)


def test_discover_refuses_a_stray_file(tmp_path):
    _write(tmp_path, "0001_a.up.sql")
    _write(tmp_path, "0001_a.down.sql")
    _write(tmp_path, "fix.sql")
    with pytest.raises(runner.MigrationError, match="fix.sql"):
        runner.discover(tmp_path)


# ── Against Postgres ──

@pytest.fixture
def pg():
    migrate_dsn, app_dsn = require_pg()
    runner.migrate_up(migrate_dsn)
    yield migrate_dsn, app_dsn
    runner.migrate_up(migrate_dsn)      # leave the newest schema for the other tests


_PG_ATTVER = re.compile(r"pg_attver=\d+")
_PG_ATTVER_ONLY = re.compile(r"^ALTER TABLE ONLY \S+ ALTER COLUMN \S+ SET \(pg_attver=\d+\);$")


def _pg_dump(dsn: str) -> str:
    """pg_dump --schema-only, without lines that differ run to run."""
    exe = os.environ.get(PG_DUMP_ENV) or shutil.which("pg_dump")
    if not exe:
        pytest.fail(f"pg_dump (version 18) must be on PATH or named by {PG_DUMP_ENV}")
    done = subprocess.run([exe, "--schema-only", "--dbname", dsn],
                          capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    keep = []
    for line in done.stdout.splitlines():
        if not line.strip() or line.startswith("--"):
            continue
        if line.startswith(("\\restrict", "\\unrestrict")):  # a random key per run
            continue
        # The flint-forge image stamps each column with a per-create attribute
        # option (pg_attver=<n>); it differs every time a column is created.
        if _PG_ATTVER_ONLY.match(line):
            continue
        keep.append(_PG_ATTVER.sub("pg_attver=N", line))
    return "\n".join(keep)


def _catalog(dsn: str) -> dict:
    """What the schema is, from the catalog: columns, indexes, constraints,
    functions and grants in schema public."""
    import psycopg

    queries = {
        "columns": """SELECT table_name, column_name, data_type, collation_name,
                             column_default, is_nullable, is_identity
                      FROM information_schema.columns WHERE table_schema = 'public'
                      ORDER BY 1, 2""",
        "indexes": """SELECT tablename, indexname, indexdef FROM pg_indexes
                      WHERE schemaname = 'public' ORDER BY 1, 2""",
        "constraints": """SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid)
                          FROM pg_constraint WHERE connamespace = 'public'::regnamespace
                          ORDER BY 1, 2""",
        "functions": """SELECT p.oid::regprocedure::text, md5(pg_get_functiondef(p.oid))
                        FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace
                        ORDER BY 1""",
        "grants": """SELECT table_name, grantee, privilege_type
                     FROM information_schema.role_table_grants
                     WHERE table_schema = 'public' ORDER BY 1, 2, 3""",
    }
    with psycopg.connect(dsn, autocommit=True) as conn:
        return {k: [tuple(r) for r in conn.execute(q).fetchall()] for k, q in queries.items()}


def test_up_down_up_gives_the_same_schema(pg):
    migrate_dsn, _ = pg
    first_dump, first_catalog = _pg_dump(migrate_dsn), _catalog(migrate_dsn)

    reverted = runner.migrate_down(migrate_dsn, 0)
    assert [m.version for m in reverted] == list(range(EXPECTED_SCHEMA_VERSION, 0, -1))
    emptied = _catalog(migrate_dsn)
    assert {c[0] for c in emptied["columns"]} == {"schema_version"}
    assert emptied["functions"] == []

    runner.migrate_up(migrate_dsn)
    assert _pg_dump(migrate_dsn) == first_dump
    assert _catalog(migrate_dsn) == first_catalog
    assert runner.status(migrate_dsn).current == EXPECTED_SCHEMA_VERSION


def test_every_migration_reverses_cleanly_on_its_own(pg):
    migrate_dsn, _ = pg
    runner.migrate_down(migrate_dsn, 0)
    at = {0: _catalog(migrate_dsn)}
    for version in range(1, EXPECTED_SCHEMA_VERSION + 1):
        runner.migrate_up(migrate_dsn, target=version)
        at[version] = _catalog(migrate_dsn)
    for version in range(EXPECTED_SCHEMA_VERSION, 0, -1):
        runner.migrate_down(migrate_dsn, version - 1)
        assert _catalog(migrate_dsn) == at[version - 1], f"down from {version}"


def test_schema_version_is_the_newest_migration(pg):
    migrate_dsn, app_dsn = pg
    state = runner.status(migrate_dsn)
    assert (state.current, state.latest, state.pending) == (
        EXPECTED_SCHEMA_VERSION, len(runner.discover()), 0)
    assert storage.read_one(app_dsn, "SELECT MAX(version) FROM schema_version") == (
        EXPECTED_SCHEMA_VERSION,)


@pytest.mark.asyncio
@pytest.mark.parametrize("ddl", [
    "CREATE TABLE sellbird_probe (x text)",
    "ALTER TABLE companies ADD COLUMN probe text",
    "DROP TABLE settings",
    "TRUNCATE settings",
    "CREATE FUNCTION sellbird_probe() RETURNS int LANGUAGE sql AS 'SELECT 1'",
    "INSERT INTO schema_version (version, name, checksum) VALUES (999, 'probe', 'x')",
])
async def test_the_runtime_role_cannot_change_the_schema(pg, ddl):
    migrate_dsn, app_dsn = pg
    before = _catalog(migrate_dsn)
    async with storage.connect(app_dsn) as db:
        with pytest.raises(storage.PermissionDenied):
            await db.execute(ddl)
    assert _catalog(migrate_dsn) == before
    assert runner.status(migrate_dsn).applied == tuple(range(1, EXPECTED_SCHEMA_VERSION + 1))


def test_migrating_with_the_runtime_role_is_refused(pg):
    _, app_dsn = pg
    with pytest.raises(runner.MigrationError, match="can't change the schema"):
        runner.migrate_up(app_dsn)


@pytest.mark.asyncio
async def test_the_app_refuses_to_run_on_a_schema_that_is_not_its_version(pg):
    migrate_dsn, app_dsn = pg
    runner.migrate_down(migrate_dsn, EXPECTED_SCHEMA_VERSION - 1)
    with pytest.raises(storage.SchemaVersionError, match="needs version"):
        await StateManager(db_path=app_dsn).init_db()
    runner.migrate_down(migrate_dsn, 0)
    with pytest.raises(storage.SchemaVersionError, match="isn't there yet"):
        await StateManager(db_path=app_dsn).init_db()
    runner.migrate_up(migrate_dsn)
    await StateManager(db_path=app_dsn).init_db()


def test_a_migration_edited_after_it_was_applied_stops_the_run(pg, tmp_path):
    migrate_dsn, _ = pg
    for m in runner.discover():
        shutil.copy(m.up, tmp_path / m.up.name)
        shutil.copy(m.down, tmp_path / m.down.name)
    edited = tmp_path / runner.discover()[-1].up.name
    edited.write_text(edited.read_text() + "\n-- edited after release\n")
    with pytest.raises(runner.MigrationError, match="was changed after it was applied"):
        runner.migrate_up(migrate_dsn, directory=tmp_path)
