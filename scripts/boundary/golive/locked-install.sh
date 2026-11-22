#!/usr/bin/env bash
# SCN-LOCK-001: the image installs only hash-locked dependencies.
# Packet:  bash scripts/boundary/golive/locked-install.sh SCN-LOCK-001
# Observation: (1) `docker build --progress=plain` of the repository exits 0 (it follows the packet's
# own `docker build -t sellbird:golive .`, so it is served from the layer cache), and the log's
# RUN line for the dependency install contains --require-hashes; (2) scripts/ci/check-lock-fresh.sh
# exits 0 (requirements.lock matches pyproject.toml; needs uv at scripts/ci/uv-version and network).
# Host architecture only; the other architecture is covered by CI.
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin scenario SCN-LOCK-001
cd "$GOLIVE_ROOT"

golive_require_tools docker uv
if [ ! -f requirements.lock ]; then
  golive_finish BLOCKED "requirements.lock does not exist: a human must run scripts/ci/lock-requirements.sh and commit it"
fi
raw="$(golive_artifact raw-locked-install-build.log)"
rc=0
DOCKER_BUILDKIT=1 docker build --progress=plain -t sellbird:golive . >> "$raw" 2>&1 || rc=$?
if [ "$rc" -ne 0 ]; then
  golive_finish FAIL "docker build exited $rc (see $(basename "$raw"))"
fi
if ! grep -E 'RUN ' "$raw" | grep -q -- '--require-hashes'; then
  golive_finish FAIL "the build log has no RUN line containing --require-hashes"
fi
golive_note "build exit 0; the dependency install step uses --require-hashes"
lraw="$(golive_artifact raw-locked-install-lockcheck.log)"
rc=0
bash "$GOLIVE_ROOT/scripts/ci/check-lock-fresh.sh" >> "$lraw" 2>&1 || rc=$?
if [ "$rc" -ne 0 ]; then
  golive_finish FAIL "check-lock-fresh.sh exited $rc (stale or missing lock, wrong uv, or no network; see $(basename "$lraw"))"
fi
golive_finish PASS "build succeeded from the committed lock (--require-hashes in the install step) and the stale-lock check exited 0"
