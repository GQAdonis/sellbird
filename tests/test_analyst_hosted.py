"""The Analyst on a hosted (Postgres) locator: the report lands in the
workspace's data folder and the runtime password never reaches the log."""

import json
import logging
from types import SimpleNamespace

import pytest

import sellbird.agents.analyst as analyst_mod
from sellbird.agents.analyst import Analyst

SECRET = "s3cret-runtime-pw"
LOCATOR = f"postgresql://sellbird_app:{SECRET}@db.example.test:5432/sellbird"


def _analyst(monkeypatch, data_dir):
    monkeypatch.setattr(analyst_mod.storage, "manages_schema", lambda loc: loc.startswith("postgresql:"))
    monkeypatch.setattr(analyst_mod, "current_home", lambda: SimpleNamespace(data_dir=data_dir))
    agent = Analyst(SimpleNamespace(db_path=LOCATOR))

    async def empty(*_a, **_k):
        return {}

    for name in ("_pipeline_summary", "_campaign_performance", "_intent_breakdown", "_stage_breakdown"):
        monkeypatch.setattr(agent, name, empty)
    monkeypatch.setattr(agent, "_generate_insights", lambda report: [])
    return agent


@pytest.mark.asyncio
async def test_hosted_report_goes_to_the_workspace_data_folder(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="sellbird.analyst")
    await _analyst(monkeypatch, tmp_path / "data").run()

    report = json.loads((tmp_path / "data" / "analytics.json").read_text(encoding="utf-8"))
    assert report["insights"] == []
    assert SECRET not in caplog.text
    assert "postgresql" not in caplog.text


@pytest.mark.asyncio
async def test_a_failed_write_logs_only_the_error_type(monkeypatch, tmp_path, caplog):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x", encoding="utf-8")
    caplog.set_level(logging.DEBUG, logger="sellbird.analyst")
    await _analyst(monkeypatch, blocker / "data").run()

    assert "Failed to write report" in caplog.text
    assert SECRET not in caplog.text
    assert str(blocker) not in caplog.text


def test_sqlite_report_stays_beside_the_database(tmp_path):
    agent = Analyst(SimpleNamespace(db_path=str(tmp_path / "sellbird.db")))
    assert agent._data_dir() == tmp_path
