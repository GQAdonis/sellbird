#!/usr/bin/env bash
# SCN-LOCK-001 negative control (a): a scratch build context whose requirements.lock has ONE hash
# altered must fail the image build IN the dependency install step (pip's --require-hashes refusal),
# not earlier or later. Packet:  neg-lock.sh SCN-LOCK-001
# The context is the .dockerignore allowlist (Dockerfile, requirements.lock, sellbird.yaml, sellbird/,
# migrations/, prompts/, skills/) copied to a temp dir; the scratch image tag is removed afterwards.
# The failing step is identified by the ERROR line naming the --require-hashes RUN and by pip's
# hash-mismatch wording in the log (unverified wording: matched case-insensitively on "hashes").
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin negativeControl SCN-LOCK-001
cd "$GOLIVE_ROOT"

golive_require_tools docker
golive_require_venv
if [ ! -f requirements.lock ]; then
  golive_finish BLOCKED "requirements.lock does not exist: a human must run scripts/ci/lock-requirements.sh and commit it"
fi
golive_scratch_new
ctx="$GOLIVE_LAST_SCRATCH"
cp Dockerfile .dockerignore requirements.lock sellbird.yaml "$ctx/"
cp -R sellbird migrations prompts skills "$ctx/"
# Alter the first hash: flip its first hex digit.
"$GOLIVE_PY" -I - "$ctx/requirements.lock" <<'PY'
import re, sys
p = sys.argv[1]
t = open(p).read()
m = re.search(r"--hash=sha256:([0-9a-f])", t)
if not m:
    raise SystemExit("no hash found in the lock")
flip = "0" if m.group(1) != "0" else "1"
t = t[:m.start(1)] + flip + t[m.end(1):]
open(p, "w").write(t)
print("altered one hash digit")
PY
if cmp -s requirements.lock "$ctx/requirements.lock"; then
  golive_finish FAIL "the scratch lock is identical to the real one; the mutation did not apply"
fi
tag="sellbird:golive-neg-lock"
GOLIVE_DOCKER_IMAGES+=("$tag")
raw="$(golive_artifact raw-neg-lock-build.log)"
rc=0
DOCKER_BUILDKIT=1 docker build --progress=plain -t "$tag" "$ctx" >> "$raw" 2>&1 || rc=$?
if [ "$rc" -eq 0 ]; then
  golive_finish FAIL "the build SUCCEEDED with an altered hash: --require-hashes is not enforced"
fi
if grep -E 'ERROR' "$raw" | grep -q -- '--require-hashes' && grep -qi 'hashes' "$raw"; then
  golive_finish PASS "build failed (exit $rc) in the dependency install step, which names --require-hashes and the hash mismatch"
fi
golive_finish FAIL "build failed (exit $rc) but not clearly in the dependency install step (see $(basename "$raw"))"
