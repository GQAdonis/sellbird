#!/usr/bin/env bash
# SCN-SHIP-002: a merge reaches the cluster with both containers ready.
#   bash scripts/boundary/golive/live-rollout.sh SCN-SHIP-002
#   bash scripts/boundary/golive/live-rollout.sh --expect-previous-digest SCN-SHIP-002   (negative control)
#
# Truth, read WITHOUT the cluster: the digest of the latest successful images.yml run on main
# (push event): its `image-digest-<sha>` artifact (DIGEST=sha256:...), else the digest line of the
# publish job's log. Observation, read-only from the cluster (`kubectl --context "$GOLIVE_KUBE_CONTEXT"
# -n sellbird`): the digest in both containers' image references of Deployment/sellbird, the ready
# container count of its single pod, and the phase of PersistentVolumeClaim sellbird-data.
# Pass: digests equal, 2 of 2 ready, claim Bound. Output: shortened digests, counts, phase.
#
# Control (--expect-previous-digest): the same comparison with the PREVIOUS successful run's digest
# (or GOLIVE_PREVIOUS_DIGEST, or - if only one release exists - a synthetic different digest, said so)
# as the expected value. The control PASSES (exit 0) when the comparison is rejected.
# Unverified assumptions (not run): `gh run list/download --json` field names and the artifact file
# layout (DIGEST= line), and that the digest in the pushed image reference equals the registry digest.
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
mode=scenario
for a in "$@"; do
  if [ "$a" = --expect-previous-digest ]; then
    mode=negativeControl
  fi
done
golive_begin "$mode" SCN-SHIP-002
cd "$GOLIVE_ROOT"
golive_require_tools gh jq kubectl
golive_kube_gate

short() { printf '%s' "${1#sha256:}" | cut -c1-12; }

runs="$(gh run list --workflow images.yml --branch main --event push --status success --limit 10 --json databaseId,headSha,createdAt)" \
  || golive_finish BLOCKED "gh could not list the images runs (login or network)"
nruns="$(jq 'length' <<< "$runs")"
if [ "$nruns" -lt 1 ]; then
  golive_finish BLOCKED "no successful images.yml run on main yet: the merge and its first run come first"
fi

# digest_of RUN_JSON_INDEX -> prints sha256:... (artifact first, then the job log)
digest_of() {
  local id sha dir d
  id="$(jq -r ".[$1].databaseId" <<< "$runs")"
  sha="$(jq -r ".[$1].headSha" <<< "$runs")"
  dir="$(mktemp -d "${TMPDIR:-/tmp}/golive.XXXXXX")"  # not golive_scratch_new: this runs in a subshell
  d=""
  if gh run download "$id" -n "image-digest-$sha" -D "$dir" > /dev/null 2>&1 && [ -f "$dir/image-digest.env" ]; then
    d="$(sed -n 's/^DIGEST=//p' "$dir/image-digest.env" | head -n 1)"
  fi
  if [ -z "$d" ]; then
    d="$(gh run view "$id" --log 2> /dev/null | grep -oE 'digest: sha256:[0-9a-f]{64}' | tail -n 1 | cut -d' ' -f2 || true)"
  fi
  rm -rf "$dir"
  printf '%s' "$d"
}

expected="$(digest_of 0)"
if [[ ! "$expected" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  golive_finish BLOCKED "could not read the published digest of the latest successful run from GitHub"
fi
latest_id="$(jq -r '.[0].databaseId' <<< "$runs")"
golive_note "GitHub's digest for run $latest_id: $(short "$expected")"

# Deployment image digests.
dep="$(k get deploy sellbird -o json)"
mapfile_digests="$(jq -r '.spec.template.spec.containers[].image' <<< "$dep" | sed -n 's/.*@\(sha256:[0-9a-f]\{64\}\)$/\1/p' | sort -u)"
ncont="$(jq -r '.spec.template.spec.containers | length' <<< "$dep")"
ndig="$(printf '%s\n' "$mapfile_digests" | grep -c . || true)"
if [ "$ndig" -ne 1 ]; then
  golive_finish FAIL "the Deployment's $ncont containers carry $ndig distinct digest(s) in their image references (expected one shared digest)"
fi
actual="$mapfile_digests"

if [ "$mode" = negativeControl ]; then
  prev="${GOLIVE_PREVIOUS_DIGEST:-}"
  note="the previous release's digest"
  if [ -z "$prev" ] && [ "$nruns" -ge 2 ]; then
    prev="$(digest_of 1)"
  fi
  if [[ ! "$prev" =~ ^sha256:[0-9a-f]{64}$ ]] || [ "$prev" = "$expected" ]; then
    prev="sha256:$(printf 'golive-no-previous-digest' | { sha256sum 2> /dev/null || shasum -a 256; } | cut -c1-64)"
    note="a synthetic different digest (no previous release exists)"
  fi
  if [ "$actual" = "$prev" ]; then
    golive_finish FAIL "the cluster digest equals the control's expected digest, so the control cannot show a mismatch"
  fi
  golive_finish PASS "comparison of the cluster digest $(short "$actual") with $note $(short "$prev") is rejected as required"
fi

if [ "$actual" != "$expected" ]; then
  golive_finish FAIL "the Deployment runs $(short "$actual") but GitHub recorded $(short "$expected") for the latest successful run"
fi
golive_note "Deployment digest equals GitHub's: $(short "$actual")"

pods="$(golive_app_pods_json)"
npods="$(jq 'length' <<< "$pods")"
if [ "$npods" -ne 1 ]; then
  golive_finish FAIL "$npods app pods present (expected exactly 1; a rollout may still be in progress)"
fi
total="$(jq '.[0].status.containerStatuses | length' <<< "$pods")"
ready="$(jq '[.[0].status.containerStatuses[] | select(.ready == true)] | length' <<< "$pods")"
pvc="$(k get pvc sellbird-data -o jsonpath='{.status.phase}' 2> /dev/null || true)"
golive_note "pod containers ready $ready of $total; claim phase ${pvc:-unknown}"
if [ "$total" -ne 2 ] || [ "$ready" -ne 2 ]; then
  golive_finish FAIL "$ready of $total containers ready (expected 2 of 2)"
fi
if [ "$pvc" != Bound ]; then
  golive_finish FAIL "PersistentVolumeClaim sellbird-data is ${pvc:-absent}, not Bound"
fi
golive_finish PASS "Deployment digest $(short "$actual") equals GitHub's; 2 of 2 containers ready; claim Bound"
