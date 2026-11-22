#!/usr/bin/env bash
# SCN-LIVE-003: nothing is sent without approval. Read-only.
#   bash scripts/boundary/golive/live-nosend.sh SCN-LIVE-003
# Truth: the outbox counts by status taken BEFORE the observed cycles: live-baseline.json written by
# live-heartbeat.sh, else a snapshot taken now (and then the script waits, up to
# GOLIVE_NOSEND_TIMEOUT_SECONDS, default 3 intervals + 2 minutes, for at least one new heartbeat row).
# Observation: the same counts after, the approval setting and the sending-paused flag, through the
# app's storage layer in the `heartbeat` container (_remote_snapshot.py). Pass: sent, approved,
# sending and failed counts unchanged (nothing left the building), approval mode on, and at least one
# cycle observed after the baseline (else BLOCKED: nothing was observed). New rows may only be pending
# review. Sending stays paused for the whole run (operator step 6); the pause cannot be told apart
# from approval mode here (contract limitation), so its value is reported, not required.
# Only counts and booleans are printed: no row, subject, body, name or address.
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin scenario SCN-LIVE-003
cd "$GOLIVE_ROOT"
golive_require_tools kubectl jq
golive_kube_gate

snap="$(golive_remote_snapshot heartbeat || true)"
if [ -z "$snap" ] || [ "$(jq -r '.ok' <<< "$snap")" != true ]; then
  err="$(jq -r '.error // .config_error // "no answer"' <<< "${snap:-null}" 2> /dev/null || echo "no answer")"
  case "$err" in
    ConfigFileNotFoundError | ConfigError) golive_finish BLOCKED "the trained configuration cannot be loaded ($err): operator step 4" ;;
  esac
  golive_finish FAIL "could not read the outbox counts through the app's storage layer ($err)"
fi
base="$EVIDENCE_DIR/live-baseline.json"
if [ ! -f "$base" ]; then
  jq -c '{taken: .now, outbox: .outbox, sending_paused: .sending_paused, require_approval: .require_approval, main_rows_total: .main_rows_total}' <<< "$snap" > "$base"
  golive_note "no baseline from live-heartbeat.sh; took one now and will wait for a cycle"
fi
rows_before="$(jq -r '.main_rows_total' "$base")"

interval="$(jq -r '.interval_minutes // 15' <<< "$snap")"
limit="${GOLIVE_NOSEND_TIMEOUT_SECONDS:-$((3 * interval * 60 + 120))}"
elapsed=0
while [ "$(jq -r '.main_rows_total' <<< "$snap")" -le "$rows_before" ]; do
  if [ "$elapsed" -ge "$limit" ]; then
    golive_finish BLOCKED "no heartbeat cycle was observed in ${limit}s after the baseline, so nothing can be said about sending"
  fi
  sleep 30
  elapsed=$((elapsed + 30))
  snap="$(golive_remote_snapshot heartbeat || true)"
  if [ -z "$snap" ] || [ "$(jq -r '.ok' <<< "$snap")" != true ]; then
    golive_finish FAIL "lost the ability to read the outbox counts while waiting"
  fi
done
rows_after="$(jq -r '.main_rows_total' <<< "$snap")"
if [ "$rows_after" -le "$rows_before" ]; then
  golive_finish BLOCKED "no heartbeat cycle was recorded since the baseline (rows $rows_before -> $rows_after): nothing observed"
fi

delta() { jq -rn --slurpfile b "$base" --argjson a "$(jq -c .outbox <<< "$snap")" --arg s "$1" '($a[$s] // 0) - ($b[0].outbox[$s] // 0)'; }
d_sent="$(delta sent)"; d_appr="$(delta approved)"; d_sending="$(delta sending)"; d_failed="$(delta failed)"; d_pend="$(delta pending_review)"
approval="$(jq -r '.require_approval' <<< "$snap")"
paused="$(jq -r '.sending_paused' <<< "$snap")"
golive_note "cycles observed: $((rows_after - rows_before)); outbox change since the baseline: sent $d_sent, approved $d_appr, sending $d_sending, failed $d_failed, pending_review $d_pend; approval mode on: $approval; sending paused: $paused"
problems=""
[ "$d_sent" = 0 ] || problems="$problems sent count changed by $d_sent;"
[ "$d_appr" = 0 ] || problems="$problems approved count changed by $d_appr;"
[ "$d_sending" = 0 ] || problems="$problems sending count changed by $d_sending;"
[ "$d_failed" = 0 ] || problems="$problems failed count changed by $d_failed;"
[ "$approval" = true ] || problems="$problems approval mode is not on ($approval);"
if [ -n "$problems" ]; then
  golive_finish FAIL "$problems"
fi
golive_finish PASS "sent count unchanged over $((rows_after - rows_before)) observed cycle(s); approval mode on; $d_pend new row(s) pending review, none approved or sent; sending paused=$paused"
