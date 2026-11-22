"""/api/sellbird/status in hosted (gateway) mode reads the heartbeat from the
database; start and stop are refused; local mode only gains "mode"."""

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import sellbird.dashboard as dash
import sellbird.config as config_mod
from sellbird.state import StateManager, parse_db_timestamp

ORIGIN = "http://127.0.0.1:5555"
INTERVAL = 15 * 60
NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
REFUSED = {"success": False, "message": "In hosted mode Sellbird is started and stopped by the "
                                       "platform, not from the dashboard."}


def test_fresh_row_is_running():
    assert dash.heartbeat_is_fresh(NOW, NOW - timedelta(seconds=INTERVAL), 3 * INTERVAL) is True


def test_row_four_intervals_old_is_not_running():
    assert dash.heartbeat_is_fresh(NOW, NOW - timedelta(seconds=4 * INTERVAL), 3 * INTERVAL) is False


def test_no_row_is_not_running():
    assert dash.heartbeat_is_fresh(NOW, None, 3 * INTERVAL) is False


def test_timestamps_parse_as_utc_from_either_backend():
    expected = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert parse_db_timestamp("2026-01-01 12:00:00") == expected          # SQLite text
    assert parse_db_timestamp("2026-01-01T12:00:00+00:00") == expected    # ISO
    assert parse_db_timestamp(datetime(2026, 1, 1, 12, 0, 0)) == expected  # naive datetime
    plus_two = datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    assert parse_db_timestamp(plus_two) == expected                       # aware datetime
    assert parse_db_timestamp(None) is None and parse_db_timestamp("junk") is None


@pytest.fixture
def env(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    db = tmp_path / "data" / "sellbird.db"
    monkeypatch.setattr(dash, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(dash, "DB_PATH", db)
    monkeypatch.setattr(dash, "PID_FILE", tmp_path / "data" / "sellbird.pid")
    monkeypatch.setattr(dash, "LOG_FILE", tmp_path / "data" / "sellbird.log")
    monkeypatch.setattr(config_mod, "load_config", lambda *a, **k: SimpleNamespace(
        usage=SimpleNamespace(heartbeat_interval_minutes=15)))
    dash.token_store.configure(tmp_path / "data" / "dashboard-token")
    asyncio.run(StateManager(db_path=str(db)).init_db())
    return {"db": db, "token": dash.token_store.get()}


@pytest.fixture
def client(env):
    with TestClient(dash.app, base_url=ORIGIN,
                    headers={"Authorization": f"Bearer {env['token']}"}) as c:
        yield c


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setattr(dash.app.state, "dashboard_mode", "gateway", raising=False)


def _row(env, minutes_ago, agent="main"):
    when = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(env["db"]) as db:
        db.execute("INSERT INTO actions (id, action_type, agent, details_json, created_at) "
                   "VALUES (?, 'idle', ?, '{}', ?)", (f"a{minutes_ago}{agent}", agent, when))


def test_gateway_status_running_for_a_fresh_row(client, env, gateway):
    _row(env, 5)
    data = client.get("/api/sellbird/status").json()
    assert data["running"] is True and data["mode"] == "gateway"
    assert data["pid"] is None and data["started_at"] is None
    assert data["stale_after_seconds"] == 45 * 60
    assert parse_db_timestamp(data["last_cycle_at"]) is not None


def test_gateway_status_stopped_for_a_row_four_intervals_old(client, env, gateway):
    _row(env, 60)
    data = client.get("/api/sellbird/status").json()
    assert data["running"] is False and data["last_cycle_at"] is not None


def test_gateway_status_stopped_with_no_rows(client, gateway):
    data = client.get("/api/sellbird/status").json()
    assert data["running"] is False and data["last_cycle_at"] is None


def test_gateway_status_ignores_rows_from_other_agents(client, env, gateway):
    _row(env, 1, agent="dashboard")
    assert client.get("/api/sellbird/status").json()["running"] is False


def test_gateway_start_and_stop_do_nothing(client, monkeypatch, gateway):
    def boom(*a, **k):
        raise AssertionError("must not spawn or signal")
    monkeypatch.setattr(dash.subprocess, "Popen", boom)
    monkeypatch.setattr(dash.os, "kill", boom)
    assert client.post("/api/sellbird/start").json() == REFUSED
    assert client.post("/api/sellbird/stop").json() == REFUSED


def test_local_status_is_unchanged_apart_from_mode(client):
    data = client.get("/api/sellbird/status").json()
    assert set(data) == {"running", "pid", "started_at", "sending_paused", "mode"}
    assert data["mode"] == "local" and data["running"] is False
