"""Build the fictional sellbird.db the storage-move tests copy into Postgres.

    python tests/fixtures/move/build_fixture.py /path/to/sellbird.db

Everything here is invented: businesses on example.test, people with generic
made-up names, 555-01xx phone numbers. The database is on the newest SQLite
schema (state.MIGRATIONS, user_version set to match) and every row names
every column and its rowid, so nothing depends on a default or the clock and
two builds hold identical contents. expected.json records the same rows,
their per-table counts and rowids; the tests derive the expected checksums
from those records.

What the data exercises: rowids with gaps (kept across the move), timestamps
in several text shapes, JSON text with irregular spacing (kept byte for
byte), non-ASCII text, embedded newlines, NULLs in text, integer and real
columns, floats with fractions, the three signal states (confirmed, proposed,
rejected) with observations naming them, a time series of one signal, outbox
rows at three points of the approval ladder, address and domain
suppressions, and tables left empty.
"""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

# table -> (columns in order, rows); each row is (rowid, *values in column order).
DATA: dict[str, tuple[tuple[str, ...], tuple[tuple, ...]]] = {
    "signal_codes": (
        ("code", "label", "description", "category", "value_type", "collector",
         "cost_note", "status", "confidence_floor", "created_at", "updated_at"),
        (
            (1, "HAS_BOOKING", "Online booking", "Whether the site offers online booking.",
             "site", "bool", "profile", "Free: reads the homepage.", "confirmed", 0.5,
             "2026-01-02 08:00:00", "2026-01-03 09:15:00"),
            (2, "SERP_RANK", "Organic rank", "Where the site ranks for its main search phrase.",
             "rank", "num", "dataforseo_serp", "Paid: one search per city.", "proposed", 0.0,
             "2026-01-02 08:00:00", "2026-01-02 08:00:00"),
            (3, "HIRING_ROLE", "Hiring for a role", "Open roles matching the hiring signals.",
             "hiring", "num", "ats", "Free: reads the public job board.", "rejected", 0.0,
             "2026-01-02 08:00:00", "2026-01-04 10:30:00"),
        ),
    ),
    "companies": (
        ("id", "name", "domain", "website", "description", "industry", "company_size",
         "location", "source", "source_url", "notes", "created_at", "updated_at",
         "tech_stack_json", "signals_json", "external_id", "phone",
         "prospects_checked_at", "profile_checked_at"),
        (
            (1, "co-alpha", "Alpha Roofing", "alpha-roofing.example.test",
             "https://alpha-roofing.example.test", "Fictional roofing contractor.", "roofing",
             "1-10", "Exampleville", "openstreetmap", "https://alpha-roofing.example.test/about",
             "", "2026-01-05T09:00:00", "2026-01-06T10:30:00.250000", '["HubSpot","Shopify"]',
             "[]", "", "+1-555-0100", "2026-01-06T10:30:00", None),
            (2, "co-beta", "Café Bêta", "cafe-beta.example.test",
             "https://cafe-beta.example.test", "Fictional café with a booking page.",
             "restaurant", "11-50", "Exampleville", "serper", "https://cafe-beta.example.test/",
             "Owner prefers mornings.", "2026-01-05T09:05:00", "2026-01-07T08:00:00",
             '[ "Intercom" ]', '[{"type": "hiring", "role": "Office manager"}]', "", "",
             None, "2026-01-07T08:00:00"),
            (5, "co-gamma", "Gamma Plumbing", "", "", "Fictional plumber with no website.",
             "plumbing", "1-10", "Exampleville", "dataforseo_listings", "", "",
             "2026-01-05T09:10:00", "2026-01-05T09:10:00", "[]", "[]", "osm:node/1001",
             "+1-555-0102", None, None),
        ),
    ),
    "prospects": (
        ("id", "company_id", "first_name", "last_name", "email", "email_verified", "phone",
         "phone_verified", "linkedin_url", "title", "seniority", "department", "source",
         "source_url", "status", "score", "personalization_notes", "company", "industry",
         "company_size", "created_at", "updated_at", "email_status", "timezone"),
        (
            (1, "pr-ada", "co-alpha", "Ada", "Example", "ada@alpha-roofing.example.test", 1, "",
             0, "", "Owner", "owner", "", "website", "https://alpha-roofing.example.test/about",
             "contacted", 82, "Mentions a storm-repair special.", "Alpha Roofing", "roofing",
             "1-10", "2026-01-06T11:00:00", "2026-01-08T09:00:00", "verified",
             "America/Chicago"),
            (2, "pr-ben", "co-beta", "Ben", "Sample", "ben@cafe-beta.example.test", 0,
             "+1-555-0110", 1, "", "Manager", "manager", "operations", "website",
             "https://cafe-beta.example.test/team", "new", 40, "", "Café Bêta", "restaurant",
             "11-50", "2026-01-07T08:30:00", "2026-01-07T08:30:00", "risky", ""),
            (4, "pr-cy", "co-alpha", "Cy", "Placeholder", "cy@alpha-roofing.example.test", 0, "",
             0, "", "Estimator", "staff", "sales", "pattern", "", "opted_out", 10, "",
             "Alpha Roofing", "roofing", "1-10", "2026-01-06T11:05:00", "2026-01-09T12:00:00",
             "guess", ""),
        ),
    ),
    "campaigns": (
        ("id", "name", "channel", "instantly_campaign_id", "sequence_json",
         "prospect_ids_json", "status", "created_at"),
        (
            (1, "cmp-spring", "Spring roofing check", "email", "",
             '[{"step": 1, "subject": "Your storm page"}, {"step": 2, "subject": "Another angle"}]',
             '["pr-ada", "pr-cy"]', "active", "2026-01-08T08:00:00"),
        ),
    ),
    "conversations": (
        ("id", "prospect_id", "campaign_id", "channel", "thread_json", "intent", "stage",
         "status", "created_at", "updated_at", "mailbox_id"),
        (
            (1, "cv-ada", "pr-ada", "cmp-spring", "email",
             '[{"from": "ada@alpha-roofing.example.test", "text": "Tell me more."}]',
             "interested", "engaged", "open", "2026-01-09T14:00:00", "2026-01-09T14:00:00", ""),
        ),
    ),
    "observations": (
        ("id", "company_id", "prospect_id", "signal_code", "collector", "value_num",
         "value_text", "confidence", "evidence_url", "observed_at", "run_id"),
        (
            (1, "ob-1", "co-beta", "", "HAS_BOOKING", "profile", 1.0, "yes", 0.9,
             "https://cafe-beta.example.test/", "2026-01-07T08:00:00", "run-1"),
            (2, "ob-2", "co-alpha", "", "HAS_BOOKING", "profile", 0.0, "no", 0.75,
             "https://alpha-roofing.example.test/", "2026-01-06T10:30:00", "run-1"),
            (3, "ob-3", "co-alpha", "", "SERP_RANK", "dataforseo_serp", 14.0,
             "roofing contractor", 1.0, "", "2026-01-06T10:31:00", "run-1"),
            (4, "ob-4", "co-alpha", "", "SERP_RANK", "dataforseo_serp", 12.0,
             "roofing contractor", 1.0, "", "2026-02-06T10:31:00", "run-2"),
            (7, "ob-5", "co-gamma", "", "HIRING_ROLE", "ats", None, "", 1.0, "",
             "2026-01-05T09:10:00", ""),
        ),
    ),
    "runs": (
        ("id", "stage", "status", "provider", "records", "cost_usd", "params_json", "error",
         "started_at", "ended_at"),
        (
            (1, "run-1", "discover", "done", "openstreetmap", 3, 0.0,
             '{"city": "Exampleville", "max_spend": 0}', "", "2026-01-05T09:00:00",
             "2026-01-05T09:12:00"),
            (2, "run-2", "profile", "failed", "", 0, 0.0125, "{}", "timeout",
             "2026-02-06T10:30:00", None),
        ),
    ),
    "outbox": (
        ("id", "campaign_id", "prospect_id", "conversation_id", "step", "kind", "to_email",
         "subject", "body", "status", "send_at", "sent_at", "provider", "message_id",
         "thread_ref", "in_reply_to", "error", "created_at", "updated_at", "approved_by",
         "mailbox_id"),
        (
            (1, "ob-msg-1", "cmp-spring", "pr-ada", "", 1, "sequence",
             "ada@alpha-roofing.example.test", "Your storm page",
             "Hi Ada,\nYour storm-repair page has no booking form.\n— Sam", "sent",
             "2026-01-08T15:00:00", "2026-01-08T15:02:11", "gmail", "<m1@mail.example.test>",
             "t-1", "", "", "2026-01-08T09:00:00", "2026-01-08T15:02:11", "you", ""),
            (2, "ob-msg-2", "cmp-spring", "pr-ada", "", 2, "sequence",
             "ada@alpha-roofing.example.test", "Another angle", "Hi Ada,\nA second thought.",
             "approved", "2026-01-12T15:00:00", None, "", "", "t-1", "<m1@mail.example.test>",
             "", "2026-01-08T09:00:00", "2026-01-10T08:00:00", "autopilot", "mb-1"),
            (3, "ob-msg-3", "", "pr-ben", "", 1, "reply", "ben@cafe-beta.example.test",
             "Re: hours", "Thanks Ben.", "pending_review", None, None, "", "", "", "", "",
             "2026-01-10T09:00:00", "2026-01-10T09:00:00", "", ""),
        ),
    ),
    "suppressions": (
        ("id", "kind", "value", "reason", "source", "created_at"),
        (
            (1, "sup-1", "address", "cy@alpha-roofing.example.test", "opt_out", "reply",
             "2026-01-09T12:00:00"),
            (2, "sup-2", "domain", "blocked.example.test", "manual", "dashboard",
             "2026-01-04T07:00:00"),
        ),
    ),
    "mailboxes": (
        ("id", "address", "display_name", "provider", "connection", "state", "paused_reason",
         "cap_override", "credential_ref", "settings_json", "warmup_started_at", "created_at"),
        (
            (1, "mb-1", "sam@sender.example.test", "Sam Sender", "smtp", "password", "active",
             "", 25, "sellbird-mailbox-mb-1",
             '{"smtp_host": "smtp.example.test", "smtp_port": 587}', "2025-12-01",
             "2025-12-01T10:00:00"),
        ),
    ),
    "campaign_mailboxes": (
        ("campaign_id", "mailbox_id"),
        (
            (1, "cmp-spring", "mb-1"),
        ),
    ),
    "actions": (
        ("id", "action_type", "agent", "details_json", "created_at"),
        (
            (1, "act-1", "send_email", "sender", '{"outbox_id": "ob-msg-1"}',
             "2026-01-08T15:02:11"),
            (2, "act-2", "opt_out", "handler", '{"prospect_id": "pr-cy"}',
             "2026-01-09T12:00:00"),
        ),
    ),
    "usage_log": (
        ("id", "date", "claude_calls", "usage_percent", "created_at", "codex_calls"),
        (
            (1, "ul-1", "2026-01-08", 12, 7.5, "2026-01-08T00:00:01", 0),
        ),
    ),
    "usage_events": (
        ("id", "created_at", "agent", "task", "session_id", "request_key", "model",
         "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens",
         "cost_usd", "duration_ms", "num_turns", "is_error", "source", "provider"),
        (),
    ),
    "processed_replies": (
        ("reply_id", "processed_at"),
        (
            (1, "<r1@mail.example.test>", "2026-01-09T14:00:00"),
        ),
    ),
    "email_patterns": (
        ("domain", "pattern", "source", "confidence", "mx_type", "is_catch_all", "updated_at"),
        (
            (1, "alpha-roofing.example.test", "{first}@{domain}", "scraped", 0.95, "google", 0,
             "2026-01-06T10:40:00"),
        ),
    ),
    "settings": (
        ("key", "value", "updated_at"),
        (
            (1, "sending_paused", "0", "2026-01-08T08:00:00"),
            (2, "stopped_company:co-gamma", "1", "2026-01-09T09:00:00"),
        ),
    ),
    "feedback": (
        ("id", "entity_type", "entity_id", "comment", "created_at"),
        (),
    ),
}


def _create_schema(db: sqlite3.Connection) -> None:
    from sellbird.state import MIGRATIONS

    for script in MIGRATIONS:
        db.executescript(script)
    db.execute(f"PRAGMA user_version = {len(MIGRATIONS)}")


def _insert(db: sqlite3.Connection, table: str, columns: tuple[str, ...],
            rows: tuple[tuple, ...]) -> None:
    stored = {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}
    if stored != set(columns):
        raise RuntimeError(
            f"{table}: the fixture names {sorted(set(columns) ^ stored)} differently from "
            "the SQLite schema; update DATA and expected.json together")
    names = ", ".join(f'"{c}"' for c in ("rowid", *columns))
    marks = ", ".join("?" for _ in range(len(columns) + 1))
    for row in rows:
        if len(row) != len(columns) + 1:
            raise RuntimeError(f"{table}: row {row[0]} has the wrong number of values")
        db.execute(f'INSERT INTO "{table}" ({names}) VALUES ({marks})', row)


def build(path: Path) -> Path:
    """Write the fixture database at ``path`` (which must not exist yet)."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        _create_schema(db)
        for table, (columns, rows) in DATA.items():
            _insert(db, table, columns, rows)
        db.commit()
    return path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python tests/fixtures/move/build_fixture.py OUTPUT.db")
    print(build(Path(sys.argv[1])))
