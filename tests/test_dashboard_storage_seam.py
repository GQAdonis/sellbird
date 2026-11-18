"""The dashboard reads and writes state through the storage seam: it follows
SELLBIRD_DATABASE_URL, not only the SQLite file at DB_PATH."""

import asyncio
import sqlite3

import pytest

import sellbird.dashboard as dash
from sellbird import inbox_routes
from sellbird.state import StateManager


def _make_db(path, name):
    async def _init():
        await StateManager(db_path=str(path)).init_db()
    asyncio.run(_init())
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO companies (id, name, domain, website, source) "
                  "VALUES ('c1', ?, 'seam.example.test', '', 'test')", (name,))


@pytest.fixture
def two_dbs(tmp_path, monkeypatch):
    default, other = tmp_path / "default.db", tmp_path / "other.db"
    _make_db(default, "Default Co")
    _make_db(other, "Url Co")
    monkeypatch.setattr(dash, "DB_PATH", default)
    return default, other


def test_locator_is_db_path_without_url(two_dbs):
    assert dash._db_locator() == str(two_dbs[0])


def test_locator_follows_database_url(two_dbs, monkeypatch):
    monkeypatch.setenv("SELLBIRD_DATABASE_URL", str(two_dbs[1]))
    assert dash._db_locator() == str(two_dbs[1])


def test_query_db_reads_default_sqlite(two_dbs):
    rows = asyncio.run(dash.query_db("SELECT name FROM companies"))
    assert [r["name"] for r in rows] == ["Default Co"]


def test_query_db_reads_the_url_locator(two_dbs, monkeypatch):
    monkeypatch.setenv("SELLBIRD_DATABASE_URL", str(two_dbs[1]))
    rows = asyncio.run(dash.query_db("SELECT name FROM companies"))
    assert [r["name"] for r in rows] == ["Url Co"]


def test_query_db_missing_database_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(dash, "DB_PATH", tmp_path / "none.db")
    assert asyncio.run(dash.query_db("SELECT 1")) == []
    assert not (tmp_path / "none.db").exists()


def test_state_and_inbox_store_use_the_locator(two_dbs, monkeypatch):
    monkeypatch.setenv("SELLBIRD_DATABASE_URL", str(two_dbs[1]))
    assert dash._state().db_path == str(two_dbs[1])
    assert inbox_routes._store().db_path == str(two_dbs[1])


def test_extra_inboxes_follow_the_locator(two_dbs, monkeypatch):
    assert dash._extra_inboxes_connected() is False
    with sqlite3.connect(two_dbs[1]) as c:
        c.execute("INSERT INTO mailboxes (id, address, provider, connection, state) VALUES ('m1', 'a@seam.example.test', 'smtp', 'x', 'active')")
    assert dash._extra_inboxes_connected() is False
    monkeypatch.setenv("SELLBIRD_DATABASE_URL", str(two_dbs[1]))
    assert dash._extra_inboxes_connected() is True


def test_conftest_clears_ambient_database_url():
    import os
    assert "SELLBIRD_DATABASE_URL" not in os.environ
    assert "SELLBIRD_MIGRATE_DATABASE_URL" not in os.environ


def test_query_db_on_postgres(monkeypatch):
    from tests.storage_contract.backends import fresh_pg_locator
    locator = fresh_pg_locator()   # skips unless SELLBIRD_TEST_PG_* are set
    monkeypatch.setenv("SELLBIRD_DATABASE_URL", locator)

    async def go():
        await StateManager(db_path=locator).init_db()
        return await dash.query_db("SELECT COUNT(*) AS n FROM companies")
    assert asyncio.run(go()) == [{"n": 0}]
