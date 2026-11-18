"""``sellbird storage move`` copies a SQLite sellbird.db into an empty Postgres, losing nothing.

The fixture is tests/fixtures/move/build_fixture.py (fictional data) and the
expectations are tests/fixtures/move/expected.json, recorded by hand from the
builder's data. Each expected checksum is computed here, from those records,
with this file's own implementation of the checksum definition in
sellbird/storage_postgres/move.py, so a slip in the tool's hashing can't hide
behind itself.

Cases that need no database run everywhere. The Postgres cases need
SELLBIRD_TEST_PG_MIGRATE_DSN and SELLBIRD_TEST_PG_APP_DSN for a throwaway
database provisioned with infra/postgres/provision.sql (see
tests/storage_contract/backends.py) and skip, saying so, without them. With
them set, a missing psycopg fails the run rather than skipping.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from sellbird.storage_postgres import EXPECTED_SCHEMA_VERSION
from sellbird.storage_postgres import cli as storage_cli
from sellbird.storage_postgres import move
from tests.storage_contract.backends import empty_tables, migrate_to_latest, require_pg

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "move"
EXPECTED = json.loads((FIXTURE_DIR / "expected.json").read_text(encoding="utf-8"))
TARGET_ENV = "SELLBIRD_TEST_MOVE_TARGET"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "sellbird_move_fixture_builder", FIXTURE_DIR / "build_fixture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


def expected_checksum(columns: list[str], rows: list[list]) -> str:
    """The checksum definition, written out independently of the tool: SHA-256
    over UTF-8 lines, the sorted column names first, then each row's values in
    that sorted order, as compact JSON with non-ASCII kept."""
    order = sorted(range(len(columns)), key=lambda i: columns[i])
    digest = hashlib.sha256()
    header = json.dumps([columns[i] for i in order], ensure_ascii=False, separators=(",", ":"))
    digest.update((header + "\n").encode("utf-8"))
    for row in rows:
        line = json.dumps([row[i] for i in order], ensure_ascii=False, separators=(",", ":"))
        digest.update((line + "\n").encode("utf-8"))
    return "sha256:" + digest.hexdigest()


def expected_table(name: str) -> tuple[int, str]:
    record = EXPECTED["tables"][name]
    return record["rows"], expected_checksum(record["columns"], record["content"])


@pytest.fixture
def fixture_db(tmp_path) -> Path:
    return builder.build(tmp_path / "sellbird.db")


# ── The recorded expectations themselves ──

def test_expected_records_cover_exactly_the_tables_the_tool_moves():
    assert set(EXPECTED["tables"]) == set(move.TABLES)
    assert EXPECTED["postgres_schema_version"] == EXPECTED_SCHEMA_VERSION


def test_expected_counts_and_rowids_agree_with_the_recorded_rows():
    total = 0
    for name, record in EXPECTED["tables"].items():
        assert record["columns"][-1] == "rowid", name
        assert record["rows"] == len(record["content"]), name
        assert record["rowids"] == [row[-1] for row in record["content"]], name
        for row in record["content"]:
            assert len(row) == len(record["columns"]), name
        total += record["rows"]
    assert total == EXPECTED["total_rows"]


def test_expected_records_match_the_builders_data():
    for name, (columns, rows) in builder.DATA.items():
        record = EXPECTED["tables"][name]
        assert record["columns"] == [*columns, "rowid"], name
        assert record["content"] == [[*row[1:], row[0]] for row in rows], name


# ── The fixture database, read as SQLite (no Postgres needed) ──

def test_fixture_is_on_the_newest_sqlite_schema(fixture_db):
    with closing(sqlite3.connect(fixture_db)) as db:
        (version,) = db.execute("PRAGMA user_version").fetchone()
    assert version == EXPECTED["sqlite_user_version"]


def test_fixture_counts_and_checksums_equal_the_recorded_values(fixture_db):
    measured = {t.name: (t.rows, t.checksum) for t in move.sqlite_checksums(fixture_db)}
    assert measured == {name: expected_table(name) for name in move.TABLES}


def test_two_builds_hold_identical_contents(tmp_path):
    first = move.sqlite_checksums(builder.build(tmp_path / "a.db"))
    second = move.sqlite_checksums(builder.build(tmp_path / "b.db"))
    assert first == second


def test_tool_checksum_follows_the_written_definition():
    columns = ["value", "id", "rowid"]
    rows = [["Café — 1", "x", 1], [None, "y", 3], [2.5, "z", 4], [7, "w", 9]]
    checksum = move.Checksum(columns)
    for row in rows:
        checksum.add(row)
    assert checksum.rows == 4
    assert checksum.hexdigest() == expected_checksum(columns, rows)


# ── Refusals decided from the source alone (nothing reaches Postgres) ──

UNREACHABLE_DSN = "postgresql://nobody@127.0.0.1:9/never"


def test_move_refuses_a_missing_source(tmp_path):
    with pytest.raises(move.MoveError, match="no SQLite database"):
        move.move(tmp_path / "absent.db", UNREACHABLE_DSN)


def test_move_refuses_a_file_that_is_not_sqlite(tmp_path):
    bogus = tmp_path / "notes.db"
    bogus.write_text("not a database, just text\n" * 200, encoding="utf-8")
    with pytest.raises(move.MoveError, match="isn't a readable SQLite database"):
        move.move(bogus, UNREACHABLE_DSN)


def test_move_refuses_a_source_on_an_older_schema(fixture_db):
    with closing(sqlite3.connect(fixture_db)) as db:
        db.execute(f"PRAGMA user_version = {EXPECTED['sqlite_user_version'] - 1}")
        db.commit()
    with pytest.raises(move.MoveError, match="sellbird status"):
        move.move(fixture_db, UNREACHABLE_DSN)


def test_move_refuses_a_source_with_a_table_it_would_leave_behind(fixture_db):
    with closing(sqlite3.connect(fixture_db)) as db:
        db.execute("CREATE TABLE custom_notes (id TEXT PRIMARY KEY, note TEXT)")
        db.commit()
    with pytest.raises(move.MoveError, match="custom_notes"):
        move.move(fixture_db, UNREACHABLE_DSN)


def test_move_never_changes_the_source(fixture_db):
    before = fixture_db.read_bytes()
    with pytest.raises(move.MoveError):
        move.move(fixture_db, UNREACHABLE_DSN)
    assert fixture_db.read_bytes() == before


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="sellbird")
    storage_cli.register(parser.add_subparsers(dest="command"))
    return parser.parse_args(argv)


def test_cli_registers_move_with_its_source_and_target_variable(fixture_db):
    args = _parse(["storage", "move", "--from", str(fixture_db), "--to-env", TARGET_ENV])
    assert args.storage_action == "move"
    assert args.from_path == str(fixture_db)
    assert args.to_env == TARGET_ENV
    assert args.func is storage_cli.cmd_storage


def test_cli_move_needs_the_target_variable_set(fixture_db, monkeypatch):
    monkeypatch.delenv(TARGET_ENV, raising=False)
    args = _parse(["storage", "move", "--from", str(fixture_db), "--to-env", TARGET_ENV])
    with pytest.raises(SystemExit):
        args.func(args)


# ── Into Postgres ──

@pytest.fixture
def empty_target() -> str:
    """The runtime role's DSN for a newest-schema database with every table empty."""
    migrate_dsn, app_dsn = require_pg()
    import psycopg  # noqa: F401  (configured for Postgres: a missing driver must fail)

    migrate_to_latest(migrate_dsn)
    empty_tables(migrate_dsn)
    return app_dsn


def _dump(dsn: str) -> dict[str, list[tuple]]:
    """Every Sellbird table's rows, every column plus rowid, in rowid order."""
    import psycopg
    from psycopg import sql

    out = {}
    with psycopg.connect(dsn, autocommit=True) as conn:
        for name in move.TABLES:
            columns = EXPECTED["tables"][name]["columns"]
            query = sql.SQL("SELECT {} FROM {} ORDER BY rowid").format(
                sql.SQL(", ").join(sql.Identifier(c) for c in columns), sql.Identifier(name))
            out[name] = [tuple(r) for r in conn.execute(query).fetchall()]
    return out


def test_move_into_an_empty_postgres_matches_the_recorded_counts_and_checksums(
        fixture_db, empty_target):
    report = move.move(fixture_db, empty_target)

    assert [t.name for t in report.tables] == list(move.TABLES)
    assert report.schema_version == EXPECTED_SCHEMA_VERSION
    assert report.total_rows == EXPECTED["total_rows"]
    assert {t.name: (t.rows, t.checksum) for t in report.tables} == {
        name: expected_table(name) for name in move.TABLES}


def test_moved_rows_read_back_exactly_as_recorded(fixture_db, empty_target):
    move.move(fixture_db, empty_target)

    dumped = _dump(empty_target)
    for name in move.TABLES:
        record = EXPECTED["tables"][name]
        assert dumped[name] == [tuple(row) for row in record["content"]], name
        assert expected_checksum(record["columns"], [list(r) for r in dumped[name]]) \
            == expected_table(name)[1], name


def test_moved_signal_confirmation_is_what_the_app_sees(fixture_db, empty_target):
    from sellbird.state import StateManager

    move.move(fixture_db, empty_target)

    async def read():
        manager = StateManager(db_path=empty_target)
        await manager.init_db()
        return (await manager.confirmed_signal_codes(),
                {s["code"]: s["status"] for s in await manager.get_signal_codes()})

    confirmed, statuses = asyncio.run(read())
    assert confirmed == {"HAS_BOOKING"}
    assert statuses == {"HAS_BOOKING": "confirmed", "SERP_RANK": "proposed",
                        "HIRING_ROLE": "rejected"}


def test_new_rows_after_the_move_follow_the_moved_rowids(fixture_db, empty_target):
    import psycopg

    move.move(fixture_db, empty_target)

    with psycopg.connect(empty_target, autocommit=True) as conn:
        (company_rowid,) = conn.execute(
            "INSERT INTO companies (id) VALUES ('co-after-move') RETURNING rowid").fetchone()
        (feedback_rowid,) = conn.execute(
            "INSERT INTO feedback (id) VALUES ('fb-after-move') RETURNING rowid").fetchone()
    assert company_rowid == max(EXPECTED["tables"]["companies"]["rowids"]) + 1
    assert feedback_rowid == 1


def test_move_into_a_target_with_sellbird_rows_is_refused_and_leaves_it_unchanged(
        fixture_db, empty_target):
    import psycopg

    with psycopg.connect(empty_target, autocommit=True) as conn:
        conn.execute("INSERT INTO settings (key, value, updated_at) "
                     "VALUES ('sending_paused', '1', '2026-03-01T00:00:00')")
    before = _dump(empty_target)

    with pytest.raises(move.TargetNotEmpty, match="settings"):
        move.move(fixture_db, empty_target)

    assert _dump(empty_target) == before


def test_move_refuses_a_target_that_is_not_migrated_to_the_current_version(fixture_db):
    migrate_dsn, app_dsn = require_pg()
    import psycopg  # noqa: F401
    from sellbird.storage_postgres import migrate

    migrate_to_latest(migrate_dsn)
    empty_tables(migrate_dsn)
    migrate.migrate_down(migrate_dsn, target=EXPECTED_SCHEMA_VERSION - 1)
    try:
        with pytest.raises(move.MoveError, match=f"version {EXPECTED_SCHEMA_VERSION}"):
            move.move(fixture_db, app_dsn)
    finally:
        migrate_to_latest(migrate_dsn)


def test_cli_move_prints_counts_and_checksums_but_never_the_connection_string(
        fixture_db, empty_target, monkeypatch, capsys):
    monkeypatch.setenv(TARGET_ENV, empty_target)
    args = _parse(["storage", "move", "--from", str(fixture_db), "--to-env", TARGET_ENV])

    args.func(args)

    out = capsys.readouterr().out
    assert empty_target not in out
    password = urlsplit(empty_target).password
    if password:
        assert password not in out
    for name in move.TABLES:
        rows, checksum = expected_table(name)
        assert any(line.split()[:3] == [name, str(rows), checksum]
                   for line in out.splitlines()), name
    assert any(line.split() == ["total", str(EXPECTED["total_rows"])]
               for line in out.splitlines())
