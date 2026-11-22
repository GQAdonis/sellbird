#!/usr/bin/env bash
# Dynamic pipeline controls: dispatch images.yml with `control=<value>` on the real repository, find
# THAT run, wait for it, and judge it from job and step conclusions (`gh run view --json`).
#
#   bash scripts/boundary/golive/pipe-control.sh failing-test     SCN-PIPE-001   (scenario)
#   bash scripts/boundary/golive/pipe-control.sh none             SCN-PIPE-001   (negative control)
#   bash scripts/boundary/golive/pipe-control.sh vulnerable-image SCN-PIPE-002   (scenario)
#
# Expectations (from the contract):
#   failing-test      the control job of the called tests workflow concludes failure (the tests job
#                     fails); publish and deploy did not succeed; the run did not succeed.
#   none              every job of the called tests workflow succeeded or was skipped (the control
#                     job skipped): the control input is what failed the previous run.
#   vulnerable-image  in the scan job the step "Vulnerability scan ..." concludes failure; the
#                     recheck step did not run; publish and deploy did not succeed.
#   all               no `image-digest-*` artifact exists for the run, and publish and deploy
#                     never concluded success (a dispatched run cannot publish or deploy).
# Safety: needs GOLIVE_ALLOW_DISPATCH=1 (the operator's approval of the three control runs). The ref
# is $GOLIVE_REF, else the current branch; main is refused unless GOLIVE_REF=main is set explicitly.
# The local HEAD must equal the remote branch tip, so the workflow dispatched is the one checked
# statically. The run is identified by "not in the run list before the dispatch, created after
# it", never by "latest". Timeouts: GOLIVE_RUN_FIND_SECONDS (default 180), GOLIVE_RUN_TIMEOUT_SECONDS
# (default 5400).
# Unverified assumptions (not run): job names of a called workflow appear as
# "<caller job name> / <called job name>" (matched here by regex on either form), and
# `gh run list/view --json` field names as used below.
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
control="${1:-}"
case "$control" in
  failing-test) scn="${2:-SCN-PIPE-001}"; kind=scenario ;;
  none) scn="${2:-SCN-PIPE-001}"; kind=negativeControl ;;
  vulnerable-image) scn="${2:-SCN-PIPE-002}"; kind=scenario ;;
  *)
    echo "usage: pipe-control.sh failing-test|none|vulnerable-image [SCN-ID]" >&2
    exit 2
    ;;
esac
golive_begin "$kind" "$scn"
cd "$GOLIVE_ROOT"
golive_require_tools gh jq git

if [ -z "${GOLIVE_ALLOW_DISPATCH:-}" ] || [ "$GOLIVE_ALLOW_DISPATCH" != 1 ]; then
  golive_finish BLOCKED "GOLIVE_ALLOW_DISPATCH=1 is not set (the operator approves the three control runs)"
fi
cur="$(git rev-parse --abbrev-ref HEAD)"
ref="${GOLIVE_REF:-$cur}"
if [ "$ref" = main ] && [ "${GOLIVE_REF:-}" != main ]; then
  golive_finish BLOCKED "refusing to dispatch on main unless GOLIVE_REF=main is set"
fi
remote_sha="$(git ls-remote --heads origin "$ref" 2> /dev/null | awk '{print $1}' | head -n 1 || true)"
if [ -z "$remote_sha" ]; then
  golive_finish BLOCKED "branch $ref is not on the remote: the operator-approved push has to happen first"
fi
if [ "$ref" = "$cur" ] && [ "$remote_sha" != "$(git rev-parse HEAD)" ]; then
  golive_finish BLOCKED "local HEAD differs from the remote tip of $ref: push (or pull) so the dispatched workflow is the checked one"
fi

before="$(gh run list --workflow images.yml --event workflow_dispatch --limit 50 --json databaseId | jq -c '[.[].databaseId]')"
t0="$(date +%s)"
t0_iso="$(golive_epoch_to_iso $((t0 - 60)))"
golive_note "dispatching images.yml control=$control on $ref"
gh workflow run images.yml -f "control=$control" --ref "$ref" > /dev/null

find_s="${GOLIVE_RUN_FIND_SECONDS:-180}"
run_id=""
elapsed=0
while [ "$elapsed" -le "$find_s" ]; do
  run_id="$(gh run list --workflow images.yml --event workflow_dispatch --limit 50 --json databaseId,createdAt \
    | jq -r --argjson old "$before" --arg t "$t0_iso" \
      '[.[] | select((.databaseId as $i | $old | index($i)) == null and .createdAt >= $t)] | sort_by(.createdAt) | .[0].databaseId // empty')"
  if [ -n "$run_id" ]; then
    break
  fi
  sleep 10
  elapsed=$((elapsed + 10))
done
if [ -z "$run_id" ]; then
  golive_finish FAIL "dispatched, but no new workflow_dispatch run appeared within ${find_s}s"
fi
golive_note "run id $run_id"
printf '%s\n' "$run_id" > "$(golive_artifact "pipe-control-$control.runid")"

limit="${GOLIVE_RUN_TIMEOUT_SECONDS:-5400}"
elapsed=0
status=""
while [ "$elapsed" -le "$limit" ]; do
  status="$(gh run view "$run_id" --json status -q .status || true)"
  if [ "$status" = completed ]; then
    break
  fi
  sleep 30
  elapsed=$((elapsed + 30))
done
if [ "$status" != completed ]; then
  golive_finish FAIL "run $run_id did not complete within ${limit}s (status ${status:-unknown})"
fi
json="$(golive_artifact "pipe-control-$control.json")"
gh run view "$run_id" --json status,conclusion,event,headSha,jobs > "$json"
run_concl="$(jq -r '.conclusion' "$json")"
event="$(jq -r '.event' "$json")"

# job_concl REGEX: the conclusion of the first job whose name matches, or "absent".
job_concl() { jq -r --arg r "$1" '[.jobs[] | select(.name | test($r)) | .conclusion] | first // "absent"' "$json"; }
# step_concl JOB_REGEX STEP_REGEX
step_concl() {
  jq -r --arg j "$1" --arg s "$2" \
    '[.jobs[] | select(.name | test($j)) | .steps[] | select(.name | test($s)) | .conclusion] | first // "absent"' "$json"
}
GATE_RX='^tests \(deploy gate\)|^test \(|^postgres$|^dependency lock is fresh$|^negative control \(failing test\)$'
gate_count() { jq -r --arg r "$GATE_RX" --arg c "$1" '[.jobs[] | select((.name | test($r)) and .conclusion == $c)] | length' "$json"; }

publish="$(job_concl '^publish to GHCR$')"
deploy="$(job_concl '^pin production overlay$')"
ctrl_job="$(job_concl 'negative control \(failing test\)')"
golive_note "run conclusion=$run_concl event=$event publish=$publish deploy=$deploy control-job=$ctrl_job gate success=$(gate_count success) failure=$(gate_count failure) skipped=$(gate_count skipped)"

problems=""
if [ "$event" != workflow_dispatch ]; then
  problems="$problems the run's event is $event;"
fi
if [ "$publish" = success ] || [ "$deploy" = success ]; then
  problems="$problems a dispatched run published or deployed (publish=$publish deploy=$deploy) - CRITICAL;"
fi
digest_artifacts="$(gh api "repos/{owner}/{repo}/actions/runs/$run_id/artifacts" --jq '[.artifacts[].name | select(startswith("image-digest-"))] | length' 2> /dev/null || echo unknown)"
if [ "$digest_artifacts" != 0 ]; then
  problems="$problems image-digest artifacts on the run: $digest_artifacts;"
fi

case "$control" in
  failing-test)
    [ "$ctrl_job" = failure ] || problems="$problems the control job concluded $ctrl_job, not failure;"
    [ "$(gate_count failure)" -ge 1 ] || problems="$problems no tests-workflow job failed;"
    [ "$run_concl" = failure ] || problems="$problems run conclusion is $run_concl;"
    ;;
  none)
    [ "$ctrl_job" = skipped ] || [ "$ctrl_job" = absent ] || problems="$problems the control job concluded $ctrl_job, not skipped;"
    [ "$(gate_count failure)" -eq 0 ] || problems="$problems $(gate_count failure) tests-workflow job(s) failed with control=none;"
    [ "$(gate_count success)" -ge 1 ] || problems="$problems no tests-workflow job succeeded;"
    ;;
  vulnerable-image)
    vuln="$(step_concl '^build and scan$' '^Vulnerability scan')"
    install="$(step_concl '^build and scan$' '^Install Trivy')"
    recheck="$(step_concl '^build and scan$' '^Recheck the image')"
    golive_note "scan job steps: install-trivy=$install vulnerability-scan=$vuln recheck=$recheck"
    if [ "$vuln" != failure ]; then
      problems="$problems the vulnerability scan step concluded $vuln, not failure (install-trivy step: $install);"
    fi
    [ "$recheck" != success ] || problems="$problems the recheck step ran after a failed scan;"
    ;;
esac

if [ -n "$problems" ]; then
  golive_finish FAIL "run $run_id control=$control:$problems"
fi
golive_finish PASS "run $run_id control=$control behaved as the contract requires (publish=$publish deploy=$deploy control-job=$ctrl_job)"
