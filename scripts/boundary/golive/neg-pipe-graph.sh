#!/usr/bin/env bash
# SCN-PIPE-001 negative control: mutated copies of the workflows must be rejected by the same graph
# check, naming the job. Copy 1: `if: always()` on the deploy job (the contract's case). Copy 2:
# publish no longer needs the tests job. The unmutated workflows must pass first.
# Packet:  neg-pipe-graph.sh SCN-PIPE-001
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin negativeControl SCN-PIPE-001
cd "$GOLIVE_ROOT"

golive_require_venv yaml
golive_scratch_new
tmp="$GOLIVE_LAST_SCRATCH"
g() { "$GOLIVE_PY" -I "$GOLIVE_DIR/_graph.py" graph "$1"; }

g .github/workflows > /dev/null || golive_finish FAIL "the real workflows already fail the graph check; the control proves nothing"
bad=0

"$GOLIVE_PY" -I "$GOLIVE_DIR/_graph.py" mutate if-always .github/workflows "$tmp/a"
rc=0
out="$(g "$tmp/a" 2>&1)" || rc=$?
printf '%s\n' "$out" | grep '^FAIL' || true
if [ "$rc" -ne 0 ] && grep -q '^FAIL SCN-PIPE-001 deploy: ' <<< "$out"; then
  golive_note "copy 1 (deploy if: always()) rejected, naming job deploy"
else
  golive_note "copy 1 NOT rejected as required (exit $rc)"
  bad=$((bad + 1))
fi

"$GOLIVE_PY" -I "$GOLIVE_DIR/_graph.py" mutate drop-tests-need .github/workflows "$tmp/b"
rc=0
out="$(g "$tmp/b" 2>&1)" || rc=$?
printf '%s\n' "$out" | grep '^FAIL' || true
if [ "$rc" -ne 0 ] && grep -q '^FAIL SCN-PIPE-001 images: ' <<< "$out"; then
  golive_note "copy 2 (publish without the tests need) rejected, naming job images"
else
  golive_note "copy 2 NOT rejected as required (exit $rc)"
  bad=$((bad + 1))
fi

if [ "$bad" -gt 0 ]; then
  golive_finish FAIL "$bad of 2 mutated workflow copies were not rejected"
fi
golive_finish PASS "both mutated copies rejected, naming the job"
