#!/usr/bin/env bash
# SCN-LIVE-001 negative control: the dashboard's pure status function heartbeat_is_fresh, given a
# newest-row timestamp FOUR heartbeat intervals old, must report not running (False). Also checked,
# so the control is not an always-False function: one interval old -> True, no row -> False.
# Local only (.venv/bin/python, no cluster). Packet:  neg-heartbeat-stale.sh SCN-LIVE-001
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin negativeControl SCN-LIVE-001
cd "$GOLIVE_ROOT"
golive_require_venv fastapi

rc=0
out="$("${GOLIVE_CLEAN_ENV[@]}" "$GOLIVE_PY" -c '
from datetime import datetime, timedelta, timezone
from sellbird import dashboard as d
now = datetime.now(timezone.utc)
interval = d.DEFAULT_HEARTBEAT_MINUTES * 60
stale_after = d.HEARTBEAT_STALE_INTERVALS * interval
stale = d.heartbeat_is_fresh(now, now - timedelta(seconds=4 * interval), stale_after)
fresh = d.heartbeat_is_fresh(now, now - timedelta(seconds=interval), stale_after)
none = d.heartbeat_is_fresh(now, None, stale_after)
print("four_intervals_old=%s one_interval_old=%s no_row=%s" % (stale, fresh, none))
' 2>&1)" || rc=$?
printf '%s\n' "$out" | tail -n 3
if [ "$rc" -ne 0 ]; then
  golive_finish FAIL "could not evaluate heartbeat_is_fresh (exit $rc)"
fi
if [ "$(printf '%s\n' "$out" | tail -n 1)" = "four_intervals_old=False one_interval_old=True no_row=False" ]; then
  golive_finish PASS "a newest row four intervals old reports not running; one interval old reports running; no row reports not running"
fi
golive_finish FAIL "heartbeat_is_fresh gave an unexpected answer"
