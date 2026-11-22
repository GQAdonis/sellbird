#!/usr/bin/env bash
# SCN-PIPE-001 and SCN-PIPE-002 (static): parse the committed workflow files and assert the job
# graph. Packet:  bash scripts/boundary/golive/pipe-graph-check.sh .github/workflows SCN-PIPE-001,SCN-PIPE-002
# The checks are in _graph.py (read its header): publish and deploy each need the tests job and the
# scan job, have no job-level always()/cancelled()/failure(), are gated on a push to main, no other
# workflow can publish or deploy; the image-ID and save step precede every scan step, a recheck
# follows the last scan, publish loads the ID-checked archive and never rebuilds. Job-level `if`
# only; a step-level `if: always()` (registry logout) is not a violation.
# Each scenario is recorded with its own status; the exit status is the worst of the two.
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin scenario SCN-PIPE-001,SCN-PIPE-002
cd "$GOLIVE_ROOT"

dir="${1:-.github/workflows}"
golive_require_venv yaml
if [ ! -d "$dir" ]; then
  golive_finish BLOCKED "workflow directory $dir not found"
fi
out="$(golive_artifact pipe-graph.txt)"
rc=0
"$GOLIVE_PY" -I "$GOLIVE_DIR/_graph.py" graph "$dir" > "$out" 2>&1 || rc=$?
cat "$out"
overall=PASS
for scn in SCN-PIPE-001 SCN-PIPE-002; do
  nfail="$(grep -c "^FAIL $scn " "$out" || true)"
  npass="$(grep -c "^PASS $scn " "$out" || true)"
  if [ "$nfail" -gt 0 ]; then
    record "$scn" FAIL "$nfail static graph check(s) failed (first: $(grep -m1 "^FAIL $scn " "$out" | cut -d' ' -f3-))"
    overall=FAIL
  elif [ "$npass" -gt 0 ]; then
    record "$scn" PASS "$npass static graph checks passed"
  else
    record "$scn" BLOCKED "the graph checker produced no verdict (exit $rc)"
    overall=FAIL
  fi
done
if [ "$overall" != PASS ] || [ "$rc" -ne 0 ]; then
  golive_finish FAIL "the job graph does not meet SCN-PIPE-001/002 (see pipe-graph.txt)"
fi
golive_finish PASS "job graph meets SCN-PIPE-001 and SCN-PIPE-002"
