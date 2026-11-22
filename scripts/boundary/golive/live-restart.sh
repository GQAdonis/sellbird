#!/usr/bin/env bash
# SCN-LIVE-002: hosted configuration survives a restart.
#   GOLIVE_ALLOW_POD_DELETE=1 bash scripts/boundary/golive/live-restart.sh SCN-LIVE-002
#   bash scripts/boundary/golive/live-restart.sh --marker-dir /tmp --expect-fail SCN-LIVE-002   (control)
#
# Primary run (the ONLY script that changes the cluster; needs GOLIVE_ALLOW_POD_DELETE=1 and
# GOLIVE_KUBE_CONTEXT, else BLOCKED):
#   1. needs one Ready app pod and a trained /data/sellbird.local.yaml (else BLOCKED);
#   2. writes a random-token marker to /data/.golive-marker (the claim) and, as the control, to
#      /tmp/.golive-marker (an emptyDir), all in the `sellbird` container;
#   3. takes `sha256sum` of /data/sellbird.local.yaml and both markers INSIDE the pod and keeps them
#      here, outside the cluster (restart-hashes.json in the evidence folder);
#   4. deletes the one pod, waits for its replacement to be Ready (GOLIVE_RESTART_TIMEOUT_SECONDS,
#      default 600), takes the three hashes again;
#   5. PASS iff the config hash and the /data marker hash are identical before and after;
#   6. removes /data/.golive-marker (cleanup). The /tmp marker is expected to be gone.
# Control (--expect-fail, --marker-dir /tmp): NO cluster access and no second delete. It runs the SAME
# comparison on the /tmp marker's before/after hashes recorded by the primary run's single delete and
# PASSES (exit 0) when the comparison reports a difference, showing it detects a file that did not
# persist. It is BLOCKED when restart-hashes.json is absent (run the primary first, in the same
# evidence folder). Only hashes, counts and statuses are printed (first 12 hex digits).
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
mdir=/data
expect_fail=""
scn=SCN-LIVE-002
while [ "$#" -gt 0 ]; do
  case "$1" in
    --marker-dir) mdir="${2:-}"; shift 2 ;;
    --expect-fail) expect_fail=1; shift ;;
    SCN-*) scn="$1"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
case "$mdir" in
  /data | /tmp) ;;
  *) echo "--marker-dir must be /data or /tmp" >&2; exit 2 ;;
esac
if [ -n "$expect_fail" ]; then
  golive_begin negativeControl "$scn"
else
  golive_begin scenario "$scn"
fi
cd "$GOLIVE_ROOT"
hashes="$EVIDENCE_DIR/restart-hashes.json"
h12() { printf '%s' "$1" | cut -c1-12; }

if [ -n "$expect_fail" ]; then
  if [ ! -f "$hashes" ]; then
    golive_finish BLOCKED "restart-hashes.json is absent: run live-restart.sh (the primary run, with its one approved pod delete) first, in this evidence folder"
  fi
  key="marker$(printf '%s' "$mdir" | tr '/' '_')"   # marker_data or marker_tmp
  b="$(jq -r --arg k "$key" '.before[$k] // empty' "$hashes")"
  a="$(jq -r --arg k "$key" '.after[$k] // "MISSING"' "$hashes")"
  if [ -z "$b" ]; then
    golive_finish BLOCKED "the primary run recorded no before-hash for the marker under $mdir"
  fi
  if [ "$a" != "$b" ]; then
    golive_finish PASS "the comparison detects that the marker under $mdir did not persist (before $(h12 "$b"), after $(h12 "$a"))"
  fi
  golive_finish FAIL "the marker under $mdir has the same hash before and after the restart: it persisted, so the control did not show a difference"
fi

# ---- primary run -------------------------------------------------------------------------------
golive_require_tools kubectl jq
if [ "${GOLIVE_ALLOW_POD_DELETE:-}" != 1 ]; then
  golive_finish BLOCKED "GOLIVE_ALLOW_POD_DELETE=1 is not set (the operator approves exactly one pod delete)"
fi
golive_kube_gate

ready_pod() {  # prints the name of the single Ready app pod, or nothing
  golive_app_pods_json | jq -r 'if length == 1 and (.[0].status.containerStatuses // [] | length) > 0
    and ([.[0].status.containerStatuses[] | select(.ready == true)] | length) == (.[0].status.containerStatuses | length)
    then .[0].metadata.name else empty end'
}
old_pod="$(ready_pod || true)"
if [ -z "$old_pod" ]; then
  golive_finish BLOCKED "there is not exactly one fully Ready app pod to restart"
fi
if ! k exec "$old_pod" -c sellbird -- test -s /data/sellbird.local.yaml 2> /dev/null; then
  golive_finish BLOCKED "/data/sellbird.local.yaml is absent: the hosted Sellbird is not trained yet (operator step 4)"
fi

token="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
for d in /data /tmp; do
  printf '%s\n' "$token" | k exec -i "$old_pod" -c sellbird -- sh -c 'umask 077; cat > "$1"' sh "$d/.golive-marker"
done

# pod_hashes POD -> JSON {config, marker_data, marker_tmp}; absent file -> "MISSING"
pod_hashes() {
  local out line h p
  out="$(k exec "$1" -c sellbird -- sh -c 'for f in /data/sellbird.local.yaml /data/.golive-marker /tmp/.golive-marker; do if [ -f "$f" ]; then sha256sum "$f"; else echo "MISSING  $f"; fi; done' 2> /dev/null)" || return 1
  local cfg="MISSING" md="MISSING" mt="MISSING"
  while IFS= read -r line; do
    h="${line%% *}"
    p="${line##* }"
    case "$p" in
      /data/sellbird.local.yaml) cfg="$h" ;;
      /data/.golive-marker) md="$h" ;;
      /tmp/.golive-marker) mt="$h" ;;
    esac
  done <<< "$out"
  jq -nc --arg c "$cfg" --arg d "$md" --arg t "$mt" '{config: $c, marker_data: $d, marker_tmp: $t}'
}
before="$(pod_hashes "$old_pod")" || golive_finish FAIL "could not hash the files in the pod before the delete"
if [ "$(jq -r '.config' <<< "$before")" = MISSING ] || [ "$(jq -r '.marker_data' <<< "$before")" = MISSING ]; then
  golive_finish FAIL "the config or the marker could not be read back before the delete"
fi
snap_before="$(golive_remote_snapshot heartbeat || true)"
if [ -n "$snap_before" ]; then
  printf '%s\n' "$snap_before" | jq -c '{main_rows_total, newest_main_at}' > "$(golive_artifact restart-heartbeat-before.json)" || true
fi
jq -n --argjson b "$before" '{before: $b}' > "$hashes"
golive_note "before the delete: config $(h12 "$(jq -r .config <<< "$before")"), marker $(h12 "$(jq -r .marker_data <<< "$before")")"

golive_note "deleting the one app pod (approved)"
k delete pod "$old_pod" --wait=true --timeout=180s > /dev/null

limit="${GOLIVE_RESTART_TIMEOUT_SECONDS:-600}"
elapsed=0
new_pod=""
while [ "$elapsed" -le "$limit" ]; do
  cand="$(ready_pod || true)"
  if [ -n "$cand" ] && [ "$cand" != "$old_pod" ]; then
    new_pod="$cand"
    break
  fi
  sleep 10
  elapsed=$((elapsed + 10))
done
if [ -z "$new_pod" ]; then
  golive_finish FAIL "no new Ready app pod within ${limit}s of the delete"
fi
after="$(pod_hashes "$new_pod")" || golive_finish FAIL "could not hash the files in the new pod"
jq -n --argjson b "$before" --argjson a "$after" '{before: $b, after: $a}' > "$hashes"
golive_note "after the restart: config $(h12 "$(jq -r .config <<< "$after")"), marker $(h12 "$(jq -r .marker_data <<< "$after")"), tmp marker $(jq -r '.marker_tmp' <<< "$after" | cut -c1-12)"
snap_after="$(golive_remote_snapshot heartbeat || true)"
if [ -n "$snap_after" ]; then
  printf '%s\n' "$snap_after" | jq -c '{main_rows_total, newest_main_at}' > "$(golive_artifact restart-heartbeat-after.json)" || true
fi

# Cleanup: remove the marker from /data (the tmp one died with the old pod).
k exec "$new_pod" -c sellbird -- rm -f /data/.golive-marker > /dev/null 2>&1 || true

cfg_same=no
mk_same=no
[ "$(jq -r .config <<< "$before")" = "$(jq -r .config <<< "$after")" ] && cfg_same=yes
[ "$(jq -r .marker_data <<< "$before")" = "$(jq -r .marker_data <<< "$after")" ] && mk_same=yes
if [ "$cfg_same" = yes ] && [ "$mk_same" = yes ]; then
  golive_finish PASS "after the pod restart /data/sellbird.local.yaml and /data/.golive-marker have identical SHA-256 (config $(h12 "$(jq -r .config <<< "$after")"))"
fi
golive_finish FAIL "after the restart: config identical=$cfg_same, /data marker identical=$mk_same"
