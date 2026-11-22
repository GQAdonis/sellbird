"""Runs INSIDE the hosted Sellbird pod (kubectl exec ... -- python -c "<this file>" [pod-start-iso]).

It reads through the app's own storage layer (StateManager, the same class the heartbeat and
the dashboard use) and prints exactly one JSON line. Output is limited to counts, booleans,
status words from a fixed list and timestamps: never a row, a subject, a body, a name or an
address. On any failure it prints {"ok": false, "error": "<exception class name>"} and nothing
else, so no connection detail can leak. Nothing is written to the database or to /data.

Fields (all optional except ok):
  ok                    true when the database was read
  interval_minutes      usage.heartbeat_interval_minutes from the trained configuration
  require_approval      channels.email.require_approval from the same file
  config_error          exception class name when the configuration could not be loaded
  sending_paused        true when the sending_paused setting is non-empty
  main_rows_total       count of action-log rows with agent = 'main' (one per heartbeat cycle)
  newest_main_at        newest such row, UTC, ISO 8601 with a Z suffix, or null
  recent_main_at        up to 20 newest row times (descending), same format
  newest_action         the newest row's action type if it is one of ACTION_WORDS, else "other"
  rows_since_start      how many of the 50 newest rows are newer than the pod start argument
  running               the dashboard status function's flag (see running_via)
  running_via           "dashboard.heartbeat_is_fresh" or "inline-formula"
  stale_after_seconds   the threshold used for `running`
  outbox                {status: count} for the seven outbox statuses
  now                   the pod's clock, UTC ISO 8601 with a Z suffix

Assumptions not run before the boundary: the StateManager API (get_outbox, get_setting,
_connect, init-free read) and sellbird.config.load_config/_find_config_file behave as in the
checked-out sources; the dashboard module imports in the heartbeat container (if it does not,
the inline formula, identical to dashboard.heartbeat_is_fresh, is used and says so).
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

ACTION_WORDS = ("idle", "prospect", "write_campaign", "send_campaigns", "quiet_hours",
                "brain_paused", "over_budget")
STATUSES = ("pending_review", "approved", "sending", "sent", "failed", "rejected", "cancelled")
STALE_INTERVALS = 3
DEFAULT_MINUTES = 15


def _iso(dt):
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_start(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


async def snapshot(start_text):
    out = {"ok": False}
    from sellbird.state import DATABASE_URL_ENV, StateManager, parse_db_timestamp

    locator = os.environ.get(DATABASE_URL_ENV, "").strip()
    if not locator:
        out["error"] = "NoDatabaseUrl"
        return out

    minutes = None
    try:
        from sellbird.config import _find_config_file, load_config
        cfg = load_config(str(_find_config_file()))
        minutes = int(cfg.usage.heartbeat_interval_minutes)
        out["interval_minutes"] = minutes
        out["require_approval"] = bool(cfg.channels.email.require_approval)
    except Exception as exc:  # noqa: BLE001 - only the class name is reported
        out["config_error"] = type(exc).__name__

    state = StateManager(db_path=locator)
    async with state._connect() as db:
        async with db.execute("SELECT COUNT(*) FROM actions WHERE agent = ?", ("main",)) as cur:
            total = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT created_at, action_type FROM actions WHERE agent = ? "
            "ORDER BY created_at DESC LIMIT 50", ("main",)
        ) as cur:
            rows = await cur.fetchall()
    times = [parse_db_timestamp(r[0]) for r in rows]
    stamps = [t for t in times if t is not None]
    newest = max(stamps) if stamps else None
    now = datetime.now(timezone.utc)
    start = _parse_start(start_text)

    out["main_rows_total"] = int(total)
    out["newest_main_at"] = _iso(newest)
    out["recent_main_at"] = [_iso(t) for t in sorted(stamps, reverse=True)[:20]]
    if rows:
        word = str(rows[0][1] or "")
        out["newest_action"] = word if word in ACTION_WORDS else "other"
    out["rows_since_start"] = (
        sum(1 for t in stamps if t > start) if start is not None else None)

    stale_after = max(minutes or DEFAULT_MINUTES, 1) * STALE_INTERVALS * 60
    try:
        from sellbird import dashboard as dash
        stale_after = max(minutes or DEFAULT_MINUTES, 1) * dash.HEARTBEAT_STALE_INTERVALS * 60
        out["running"] = bool(dash.heartbeat_is_fresh(now, newest, stale_after))
        out["running_via"] = "dashboard.heartbeat_is_fresh"
    except Exception:  # noqa: BLE001
        out["running"] = bool(newest is not None and (now - newest).total_seconds() < stale_after)
        out["running_via"] = "inline-formula"
    out["stale_after_seconds"] = stale_after

    out["sending_paused"] = bool(await state.get_setting("sending_paused"))
    counts = {}
    for status in STATUSES:
        counts[status] = len(await state.get_outbox(status=status, limit=1000000))
    out["outbox"] = counts
    out["now"] = _iso(now)
    out["ok"] = True
    return out


def main():
    start_text = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        result = asyncio.run(snapshot(start_text))
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": type(exc).__name__}
    print(json.dumps(result))


main()
