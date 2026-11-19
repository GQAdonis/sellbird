"""The storage contract: the same state operations give the same answers on
SQLite and Postgres.

Every case runs once per backend (``locator`` / ``state`` fixtures). Postgres
cases run as the runtime role and skip, saying why, without the test DSNs.
Expected values are written by hand from the documented behaviour, never
captured from a run. All data is fictional (example.test).
"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from sellbird import storage
from sellbird.mailboxes import MailboxExists, MailboxStore
from sellbird.models.company import Company
from sellbird.models.prospect import Prospect
from sellbird.state import (
    COLLEAGUE_REPLIED,
    COMPANY_STOP_KEY,
    STALE_SENDING_ERROR,
    StateManager,
)
from tests.storage_contract.backends import locator, state  # noqa: F401  (fixtures)


def _utc(delta: timedelta = timedelta(0)) -> str:
    return (datetime.now(timezone.utc).replace(tzinfo=None) + delta).isoformat()


async def _prospect(state, email, first="Ana", last="Rivera", company_id="", status="queued"):
    return await state.add_prospect(Prospect(
        first_name=first, last_name=last, title="Owner", email=email,
        email_status="verified", email_verified=True, status=status, company_id=company_id))


# ── Which backend ──

def test_sqlite_is_the_default_and_a_postgres_url_selects_postgres(monkeypatch):
    monkeypatch.delenv("SELLBIRD_DATABASE_URL", raising=False)
    assert StateManager().db_path.endswith("sellbird.db")
    assert storage.dialect(StateManager().db_path) == "sqlite"
    url = "postgresql://sellbird_app@db.example.test:5432/sellbird"
    monkeypatch.setenv("SELLBIRD_DATABASE_URL", url)
    assert StateManager().db_path == url
    assert storage.dialect(url) == "postgres"
    assert storage.manages_schema(url)


# ── Identity and dedup ──

@pytest.mark.asyncio
async def test_a_company_is_recorded_once_per_normalised_domain(state):
    first = await state.add_company(Company(name="Example Bakery", domain="Bakery.Example.test"))
    again = await state.add_company(Company(name="Example Bakery (2)", domain=" bakery.example.test"))
    assert again == first
    assert (await state.get_company(first)).name == "Example Bakery"


@pytest.mark.asyncio
async def test_a_prospect_is_recorded_once_per_email_whatever_its_case(state):
    first = await _prospect(state, "Ana@Bakery.Example.test")
    again = await _prospect(state, "ana@bakery.example.test", first="Ana B.")
    assert again == first
    assert (await state.get_prospect_by_email("ANA@bakery.example.test")).id == first


# ── Governed signal vocabulary ──

@pytest.mark.asyncio
async def test_an_unknown_signal_code_is_refused_and_nothing_is_stored(state):
    with pytest.raises(sqlite3.IntegrityError, match="unknown signal_code"):
        await state.add_observation("NOT_A_SIGNAL", company_id="co-1", value_num=1)
    with pytest.raises(sqlite3.IntegrityError):
        await state.add_observations([{"signal_code": "ALSO_NOT_A_SIGNAL", "company_id": "co-1"}])
    assert await state.get_observations() == []


@pytest.mark.asyncio
async def test_a_known_signal_is_stored_as_a_row_without_hidden_columns(state):
    await state.upsert_signal_code("HAS_BOOKING", label="Online booking", value_type="bool")
    await state.add_observation("HAS_BOOKING", company_id="co-1", value_num=1,
                                evidence_url="https://bakery.example.test/book")
    rows = await state.get_observations(company_id="co-1")
    assert len(rows) == 1
    assert rows[0]["signal_code"] == "HAS_BOOKING" and rows[0]["value_num"] == 1.0
    assert "rowid" not in rows[0]


@pytest.mark.asyncio
async def test_signals_are_only_confirmed_by_an_explicit_status(state):
    await state.upsert_signal_code("RUNS_ADS", label="Runs ads")
    assert await state.confirmed_signal_codes() == set()
    assert await state.set_signal_status("RUNS_ADS", "confirmed") is True
    await state.upsert_signal_code("RUNS_ADS", label="Runs ads, relabelled")  # re-seed
    assert await state.confirmed_signal_codes() == {"RUNS_ADS"}


@pytest.mark.asyncio
async def test_latest_only_reads_the_newest_observation_per_signal(state):
    await state.upsert_signal_code("HAS_BOOKING", value_type="bool")
    await state.upsert_signal_code("RUNS_ADS", value_type="bool")
    await state.add_observation("HAS_BOOKING", company_id="co-1", value_num=1,
                                observed_at="2026-01-05 09:00:00")
    await state.add_observation("HAS_BOOKING", company_id="co-1", value_num=0,
                                observed_at="2026-03-05 09:00:00")
    await state.add_observation("RUNS_ADS", company_id="co-1", value_num=1,
                                observed_at="2026-02-01 09:00:00")
    rows = await state.get_observations(company_id="co-1", latest_only=True)
    assert [(r["signal_code"], r["value_num"]) for r in rows] == [
        ("HAS_BOOKING", 0.0), ("RUNS_ADS", 1.0)]


# ── Outbox: double-send guard and exactly-once claim ──

@pytest.mark.asyncio
async def test_the_same_sequence_step_cannot_be_queued_twice(state):
    kwargs = dict(prospect_id="p-1", to_email="ana@bakery.example.test", subject="Hello",
                  body="A note.", send_at=_utc(), campaign_id="camp-1", step=1)
    assert await state.add_outbox_item(**kwargs) is not None
    assert await state.add_outbox_item(**kwargs) is None
    assert len(await state.get_outbox()) == 1


@pytest.mark.asyncio
async def test_an_approved_due_item_is_claimed_once(state):
    item = await state.add_outbox_item(prospect_id="p-1", to_email="ana@bakery.example.test",
                                       subject="Hello", body="A note.", send_at=_utc(-timedelta(minutes=1)),
                                       status="approved", campaign_id="camp-1")
    assert await state.claim_outbox_item(item) is True
    assert await state.claim_outbox_item(item) is False
    assert (await state.get_outbox_item(item))["status"] == "sending"


@pytest.mark.asyncio
async def test_unapproved_or_future_items_are_never_claimed(state):
    pending = await state.add_outbox_item(prospect_id="p-1", to_email="ana@bakery.example.test",
                                          subject="Hello", body="A note.", send_at=_utc(),
                                          campaign_id="camp-1", step=1)
    future = await state.add_outbox_item(prospect_id="p-1", to_email="ana@bakery.example.test",
                                         subject="Again", body="A note.",
                                         send_at=_utc(timedelta(days=2)), status="approved",
                                         campaign_id="camp-1", step=2)
    assert await state.claim_outbox_item(pending) is False
    assert await state.claim_outbox_item(future) is False
    assert (await state.get_outbox_item(pending))["status"] == "pending_review"
    assert (await state.get_outbox_item(future))["status"] == "approved"


@pytest.mark.asyncio
async def test_an_abandoned_claim_fails_with_a_check_your_sent_folder_note(state, locator):
    old = await state.add_outbox_item(prospect_id="p-1", to_email="ana@bakery.example.test",
                                      subject="Old", body="A note.", send_at=_utc(),
                                      status="approved", campaign_id="camp-1", step=1)
    fresh = await state.add_outbox_item(prospect_id="p-2", to_email="ben@bakery.example.test",
                                        subject="New", body="A note.", send_at=_utc(),
                                        status="approved", campaign_id="camp-1", step=1)
    assert await state.claim_outbox_item(old) and await state.claim_outbox_item(fresh)
    async with storage.connect(locator) as db:
        await db.execute("UPDATE outbox SET updated_at = ? WHERE id = ?",
                         (_utc(-timedelta(hours=1)), old))
        await db.commit()
    assert await state.fail_stale_sending_outbox() == 1
    stale = await state.get_outbox_item(old)
    assert (stale["status"], stale["error"]) == ("failed", STALE_SENDING_ERROR)
    assert (await state.get_outbox_item(fresh))["status"] == "sending"


@pytest.mark.asyncio
async def test_items_with_no_send_time_come_first_as_in_sqlite(state):
    dated = await state.add_outbox_item(prospect_id="p-1", to_email="ana@bakery.example.test",
                                        subject="Dated", body="A note.",
                                        send_at="2026-01-01T08:00:00", status="approved",
                                        kind="reply")
    undated = await state.add_outbox_item(prospect_id="p-2", to_email="ben@bakery.example.test",
                                          subject="Undated", body="A note.", send_at=None,
                                          status="approved", kind="reply")
    assert [i["id"] for i in await state.get_outbox(status="approved")] == [undated, dated]


@pytest.mark.asyncio
async def test_sends_today_count_only_todays_utc_sends(state):
    today = await state.add_outbox_item(prospect_id="p-1", to_email="ana@bakery.example.test",
                                        subject="Today", body="A note.", send_at=_utc(),
                                        status="sent", kind="reply")
    earlier = await state.add_outbox_item(prospect_id="p-2", to_email="ben@bakery.example.test",
                                          subject="Earlier", body="A note.", send_at=_utc(),
                                          status="sent", kind="reply")
    await state.update_outbox_item(today, sent_at=_utc())
    await state.update_outbox_item(earlier, sent_at=_utc(-timedelta(days=2)))
    assert await state.count_outbox_sent_today() == 1
    assert await state.count_outbox_sent_today(kind="sequence") == 0


# ── Opt-out, suppression, company stop ──

@pytest.mark.asyncio
async def test_an_opt_out_is_permanent_until_a_human_undoes_it(state):
    pid = await _prospect(state, "ana@bakery.example.test", status="opted_out")
    await state.log_action("opt_out", "handler", {"prospect_id": pid})
    await state.update_prospect_status(pid, "replied")
    assert (await state.get_prospect(pid)).status == "opted_out"
    assert await state.undo_opt_out(pid, {"by": "test"}) is True
    assert (await state.get_prospect(pid)).status == "replied"
    assert await state.undo_opt_out(pid) is False
    history = await state.opt_out_history(pid)
    assert [h["action"] for h in history] == ["opt_out", "opt_out_undone"]


@pytest.mark.asyncio
async def test_a_suppressed_domain_covers_its_subdomains(state):
    assert await state.add_suppression("domain", "https://www.Blocked.example.test/contact") is True
    assert await state.add_suppression("domain", "blocked.example.test") is False
    assert await state.is_suppressed("pat@mail.blocked.example.test") == "manual"
    assert await state.is_suppressed("pat@notblocked.example.test") is None
    assert [s["value"] for s in await state.list_suppressions()] == ["blocked.example.test"]


@pytest.mark.asyncio
async def test_a_reply_stops_cold_email_to_the_rest_of_the_company(state):
    company = await state.add_company(Company(name="Example Bakery", domain="bakery.example.test"))
    ana = await _prospect(state, "ana@bakery.example.test", company_id=company, status="replied")
    ben = await _prospect(state, "ben@bakery.example.test", first="Ben", last="Okafor",
                          company_id=company)
    item = await state.add_outbox_item(prospect_id=ben, to_email="ben@bakery.example.test",
                                       subject="Hello", body="A note.", send_at=_utc(),
                                       campaign_id="camp-1", step=1)
    assert await state.stop_company(ana) == 1
    cancelled = await state.get_outbox_item(item)
    assert (cancelled["status"], cancelled["error"]) == ("cancelled", f"{COLLEAGUE_REPLIED} (Ana Rivera)")
    assert await state.get_setting(COMPANY_STOP_KEY + ana) == "Ana Rivera"
    assert await state.stop_company(ana) == 0          # recorded again, nothing left to cancel
    assert await state.colleague_who_replied(ben) == "Ana Rivera"


# ── Settings, usage, patterns, feedback ──

@pytest.mark.asyncio
async def test_settings_upsert_and_delete(state):
    await state.set_setting("sending_paused", "1")
    await state.set_setting("sending_paused", "0")
    assert await state.get_setting("sending_paused") == "0"
    assert await state.increment_setting("bounce_count", 2) == 2
    await state.delete_setting("sending_paused")
    assert await state.get_setting("sending_paused", "unset") == "unset"


@pytest.mark.asyncio
async def test_usage_counts_and_sums_come_back_as_plain_numbers(state):
    await state.increment_usage("claude")
    await state.increment_usage("claude")
    assert await state.get_usage_today("claude") == 2
    assert await state.record_usage_event(agent="writer", request_key="req-1", input_tokens=120,
                                          output_tokens=30, cost_usd=0.25) is True
    assert await state.record_usage_event(agent="writer", request_key="req-1") is False
    today = (await state.usage_totals())["today"]
    assert today["input_tokens"] == 120 and type(today["input_tokens"]) is int
    assert today["cost_usd"] == 0.25


@pytest.mark.asyncio
async def test_an_email_pattern_only_gives_way_to_equal_or_better_confidence(state):
    await state.save_email_pattern("bakery.example.test", "{first}", "site", 0.9)
    await state.save_email_pattern("bakery.example.test", "{f}{last}", "guess", 0.5)
    kept = await state.get_email_pattern("bakery.example.test")
    assert (kept["pattern"], kept["confidence"]) == ("{first}", 0.9)
    await state.save_email_pattern("bakery.example.test", "{first}.{last}", "verified", 0.95)
    better = await state.get_email_pattern("bakery.example.test")
    assert (better["pattern"], better["confidence"]) == ("{first}.{last}", 0.95)


@pytest.mark.asyncio
async def test_feedback_lives_in_a_migrated_table(state):
    fid = await state.add_feedback("contact", "p-1", "Warm lead, call first")
    rows = await state.get_feedback("contact", "p-1")
    assert [(r["id"], r["comment"]) for r in rows] == [(fid, "Warm lead, call first")]


# ── Mailboxes: a duplicate address keeps SQLite's message ──

@pytest.mark.asyncio
async def test_connecting_an_address_twice_says_it_exists(state, locator):
    store = MailboxStore(db_path=locator)
    await store.add_mailbox(mailbox_id="mb-1", address="sales@bakery.example.test",
                            provider="smtp", connection="smtp")
    with pytest.raises(MailboxExists):
        await store.add_mailbox(mailbox_id="mb-2", address="Sales@bakery.example.test",
                                provider="smtp", connection="smtp")


# ── The connection contract itself ──

@pytest.mark.asyncio
async def test_a_failed_statement_leaves_the_rest_of_the_transaction_usable(state, locator):
    async with storage.connect(locator) as db:
        await db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("a", "1"))
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed: settings.key"):
            await db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("a", "2"))
        await db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("b", "3"))
        await db.commit()
    assert (await state.get_setting("a"), await state.get_setting("b")) == ("1", "3")


@pytest.mark.asyncio
async def test_closing_without_commit_discards_the_write(state, locator):
    async with storage.connect(locator) as db:
        await db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("uncommitted", "1"))
    assert await state.get_setting("uncommitted", "absent") == "absent"


@pytest.mark.asyncio
async def test_rows_read_by_name_and_position(state, locator):
    await state.set_setting("greeting", "hello")
    async with storage.connect(locator) as db:
        db.row_factory = sqlite3.Row
        async with db.execute("SELECT key, value FROM settings WHERE key = ?", ("greeting",)) as cur:
            row = await cur.fetchone()
    assert (row[0], row["VALUE"], dict(row)) == ("greeting", "hello", {"key": "greeting", "value": "hello"})


@pytest.mark.asyncio
async def test_read_one_answers_synchronously_through_the_seam(state, locator):
    await state.add_company(Company(name="Example Bakery", domain="bakery.example.test"))
    assert storage.read_one(locator, "SELECT name FROM companies WHERE domain = ?",
                            ("bakery.example.test",)) == ("Example Bakery",)
    assert storage.read_one(locator, "SELECT name FROM companies WHERE domain = ?",
                            ("none.example.test",)) is None
