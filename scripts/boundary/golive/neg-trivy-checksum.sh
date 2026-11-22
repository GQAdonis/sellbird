#!/usr/bin/env bash
# SCN-PIPE-002 negative control (a): scripts/ci/verify-trivy.sh given a WRONG SHA-256 exits non-zero
# before any scan can run. Also: a placeholder is refused (exit 2), the right checksum passes (exit 0,
# so the control is not just always-failing), and the workflow runs the script before its first scan
# step. Packet:  neg-trivy-checksum.sh SCN-PIPE-002
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin negativeControl SCN-PIPE-002
cd "$GOLIVE_ROOT"

golive_require_venv yaml
golive_scratch_new
tmp="$GOLIVE_LAST_SCRATCH"
printf 'golive checksum fixture\n' > "$tmp/archive.tgz"
good="$(golive_sha256 "$tmp/archive.tgz")"
wrong="$(printf '%064d' 0)"
v() { bash "$GOLIVE_ROOT/scripts/ci/verify-trivy.sh" "$@"; }

rc=0
v "$tmp/archive.tgz" "$good" > /dev/null 2>&1 || rc=$?
if [ "$rc" -ne 0 ]; then
  golive_finish FAIL "the verify script rejected the CORRECT checksum (exit $rc)"
fi
rc=0
v "$tmp/archive.tgz" "$wrong" > "$tmp/wrong.out" 2>&1 || rc=$?
if [ "$rc" -eq 0 ]; then
  golive_finish FAIL "the verify script ACCEPTED a wrong checksum"
fi
golive_note "wrong checksum rejected with exit $rc"
rc2=0
v "$tmp/archive.tgz" "REPLACE_WITH_SHA256_OF_TRIVY_0.70.0_Linux-64bit.tar.gz" > /dev/null 2>&1 || rc2=$?
if [ "$rc2" -ne 2 ]; then
  golive_finish FAIL "a placeholder checksum gave exit $rc2, expected 2 (fail closed)"
fi
if ! "$GOLIVE_PY" -I "$GOLIVE_DIR/_graph.py" trivy-order .github/workflows; then
  golive_finish FAIL "images.yml does not run verify-trivy.sh before its first scan step"
fi
golive_finish PASS "wrong checksum exit $rc and placeholder exit $rc2 are refused, the right one passes, and the check precedes every scan"
