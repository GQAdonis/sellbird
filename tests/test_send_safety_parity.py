"""Sending safety is identical on SQLite and Postgres.

Each scenario in tests/storage_contract/fixtures/sending_safety.json (quiet
hours, the daily send limit, opt-out and suppression, the approval ladder) is
seeded into a fresh database on each backend, the Sender drains its outbox
once into a recording mailbox (no email leaves the machine), and what was sent
and what became of every outbox row must equal the hand-authored expectation.
Postgres runs as the runtime role and skips, saying why, without the test DSNs.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sellbird.models.prospect import Prospect
from sellbird.state import StateManager
from tests.storage_contract.backends import BACKENDS, fresh_locator
from tests.test_outbox_native import Cfg, FakeProvider, make_sender

FIXTURE = json.loads(
    (Path(__file__).parent / "storage_contract" / "fixtures" / "sending_safety.json").read_text())
DEFAULTS = FIXTURE["defaults"]


def _at(minutes: float) -> str:
    return (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=minutes)).isoformat()


async def _seed(state: StateManager, scenario: dict) -> dict[str, str]:
    people = {}
    for p in scenario["prospects"]:
        people[p["key"]] = (await state.add_prospect(Prospect(
            first_name=p["first_name"], last_name=p["last_name"], title="Owner",
            email=p["email"], email_status="verified", email_verified=True,
            status=p["status"])), p["email"])
    for s in scenario.get("suppressions", []):
        await state.add_suppression(s["kind"], s["value"])
    for n in range(scenario.get("sent_today", 0)):
        done = await state.add_outbox_item(
            prospect_id=f"earlier-{n}", to_email=f"earlier-{n}@sent.example.test",
            subject=DEFAULTS["subject"], body=DEFAULTS["body"], send_at=_at(-120),
            status="sent", kind="reply")
        await state.update_outbox_item(done, sent_at=_at(-1))
    items = {}
    for spec in scenario["items"]:
        pid, email = people[spec["prospect"]]
        item_id = await state.add_outbox_item(
            prospect_id=pid, to_email=email, subject=DEFAULTS["subject"], body=DEFAULTS["body"],
            send_at=_at(spec["send_in_minutes"]), campaign_id=DEFAULTS["campaign_id"],
            step=spec["step"], kind=spec["kind"])
        if spec["approval"] == "human":
            assert await state.approve_outbox(item_id) == 1
        elif spec["approval"] == "rejected":
            assert await state.reject_outbox_item(item_id) == 1
        items[spec["key"]] = item_id
    return items


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("scenario", FIXTURE["scenarios"], ids=lambda s: s["name"])
async def test_sending_safety_matches_the_expectation(backend, scenario, tmp_path, monkeypatch):
    state = StateManager(db_path=fresh_locator(backend, tmp_path))
    await state.init_db()
    monkeypatch.setattr(Cfg.channels.email, "max_daily_sends",
                        scenario.get("max_daily_sends", DEFAULTS["max_daily_sends"]))
    items = await _seed(state, scenario)

    mailbox = FakeProvider()              # records sends; nothing leaves the machine
    sender = make_sender(state, mailbox)
    sender.cold_only = scenario.get("cold_only", False)
    await sender._drain_due()

    assert sorted(m["to"] for m in mailbox.sent) == sorted(scenario["expected_sent"])
    for key, expected in scenario["expected_items"].items():
        row = await state.get_outbox_item(items[key])
        assert {k: row[k] for k in expected} == expected, f"{scenario['name']}: {key}"
