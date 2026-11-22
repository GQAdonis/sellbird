#!/usr/bin/env bash
# SCN-LIVE-001: the hosted Sellbird runs heartbeat cycles.
#   bash scripts/boundary/golive/live-heartbeat.sh SCN-LIVE-001
# Truth: the app pod's start time (kubectl, read-only). Observation: through the app's own storage
# layer inside the `heartbeat` container (_remote_snapshot.py): count of heartbeat rows (the action
# log rows with agent 'main'), the newest row's time, how many recent rows are newer than the pod
# start, and the dashboard status function's running flag. Pass: at least one row newer than the pod
# start AND running, polled for up to 3 heartbeat intervals + 2 minutes (GOLIVE_HEARTBEAT_TIMEOUT_SECONDS).
# BLOCKED (not FAIL) when the hosted Sellbird is not trained, or its newest cycle is a 'brain_paused'
# cycle (the Claude login does not work). A cycle may be an idle cycle: this proves the loop, not
# prospecting quality. Also writes live-baseline.json (outbox counts before the observation), which
# live-nosend.sh uses as its "before". Only counts, booleans and timestamps are printed.
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin scenario SCN-LIVE-001
cd "$GOLIVE_ROOT"
golive_require_tools kubectl jq
golive_kube_gate

pods="$(golive_app_pods_json)"
if [ "$(jq 'length' <<< "$pods")" -ne 1 ]; then
  golive_finish BLOCKED "there is not exactly one app pod"
fi
start="$(jq -r '.[0].status.startTime' <<< "$pods")"
if [[ ! "$start" =~ ^[0-9T:Z-]{20}$ ]]; then
  golive_finish BLOCKED "the pod start time is not available yet"
fi
if ! k exec deploy/sellbird -c heartbeat -- test -s /data/sellbird.local.yaml 2> /dev/null; then
  golive_finish BLOCKED "the hosted Sellbird is not trained: /data/sellbird.local.yaml is absent (operator step 4)"
fi
restarts="$(jq '[.[0].status.containerStatuses[] | select(.name == "heartbeat") | .restartCount] | first // 0' <<< "$pods")"
golive_note "pod started $start; heartbeat container restarts: $restarts"

snap="$(golive_remote_snapshot heartbeat "$start" || true)"
if [ -z "$snap" ] || [ "$(jq -r '.ok' <<< "$snap")" != true ]; then
  err="$(jq -r '.error // .config_error // "no answer"' <<< "${snap:-null}" 2> /dev/null || echo "no answer")"
  case "$err" in
    ConfigFileNotFoundError | ConfigError) golive_finish BLOCKED "the trained configuration cannot be loaded ($err): operator step 4" ;;
  esac
  golive_finish FAIL "could not read the heartbeat rows through the app's storage layer ($err)"
fi
if [ ! -f "$EVIDENCE_DIR/live-baseline.json" ]; then
  jq -c '{taken: .now, outbox: .outbox, sending_paused: .sending_paused, require_approval: .require_approval, main_rows_total: .main_rows_total}' <<< "$snap" > "$EVIDENCE_DIR/live-baseline.json"
fi
if [ -f "$EVIDENCE_DIR/restart-heartbeat-before.json" ]; then
  golive_note "before the restart: $(cat "$EVIDENCE_DIR/restart-heartbeat-before.json")"
fi

interval="$(jq -r '.interval_minutes // 15' <<< "$snap")"
limit="${GOLIVE_HEARTBEAT_TIMEOUT_SECONDS:-$((3 * interval * 60 + 120))}"
elapsed=0
while :; do
  since="$(jq -r '.rows_since_start // 0' <<< "$snap")"
  running="$(jq -r '.running' <<< "$snap")"
  newest="$(jq -r '.newest_main_at // "none"' <<< "$snap")"
  action="$(jq -r '.newest_action // "none"' <<< "$snap")"
  golive_note "rows total $(jq -r .main_rows_total <<< "$snap"); newest $newest ($action); newer than pod start: $since; running=$running"
  if [ "$action" = brain_paused ]; then
    golive_finish BLOCKED "the newest cycle is a brain_paused cycle: the Claude login does not work (operator step 4); no model work is being done"
  fi
  if [ "$since" -ge 1 ] && [ "$running" = true ]; then
    golive_finish PASS "$since heartbeat row(s) newer than the pod start, newest $newest ($action), status running via $(jq -r '.running_via' <<< "$snap"), interval ${interval} min"
  fi
  if [ "$elapsed" -ge "$limit" ]; then
    break
  fi
  sleep 30
  elapsed=$((elapsed + 30))
  snap="$(golive_remote_snapshot heartbeat "$start" || true)"
  if [ -z "$snap" ] || [ "$(jq -r '.ok' <<< "$snap")" != true ]; then
    golive_finish FAIL "lost the ability to read the heartbeat rows while waiting"
  fi
done
golive_finish FAIL "no heartbeat row newer than the pod start (running=$running, rows newer: $since) after ${limit}s"
