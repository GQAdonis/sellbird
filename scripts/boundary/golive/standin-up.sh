#!/usr/bin/env bash
# Packet command `run-standin`: bring up the local Postgres 18 / Kratos / flint-gate / Sellbird
# stand-in (infra/local/compose.yaml) on the free ports preflight.sh chose, so suite.sh runs the
# Postgres and gateway tests with zero skips and neg-approved-send.sh has a Postgres to use.
#
#   bash scripts/boundary/golive/standin-up.sh
#
# Needs the image `sellbird:golive` (packet command `build`). compose.yaml uses the tag
# `sellbird:boundary` with pull_policy never, so this retags golive as boundary (a local tag only;
# cleanup: docker image rm sellbird:boundary). scripts/local/make-env.sh calls plain python3, which
# may be a refusing shim on this machine: a wrapper `python3` that runs .venv/bin/python is put first
# on PATH for that one call. make-env.sh resets only the stand-in's own containers and volumes and
# prints no secret. Cleanup after the run: docker compose -f infra/local/compose.yaml down -v
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin support STANDIN-UP
cd "$GOLIVE_ROOT"

golive_require_tools docker openssl
golive_require_venv yaml
golive_load_ports
if [ -z "${SELLBIRD_LOCAL_PG_PORT:-}" ] || [ -z "${SELLBIRD_LOCAL_GATE_PORT:-}" ] || [ -z "${SELLBIRD_LOCAL_DIRECT_PORT:-}" ]; then
  golive_finish BLOCKED "no stand-in ports: run preflight.sh first (it writes ports.env)"
fi
if ! docker image inspect sellbird:golive > /dev/null 2>&1; then
  golive_finish BLOCKED "image sellbird:golive not found: run docker build -t sellbird:golive . first"
fi
docker tag sellbird:golive sellbird:boundary
golive_note "tagged sellbird:golive as sellbird:boundary for compose"

raw="$(golive_artifact raw-standin-up.log)"
golive_python3_shim_new
rc=0
PATH="$GOLIVE_SHIM_DIR:$PATH" bash "$GOLIVE_ROOT/scripts/local/make-env.sh" >> "$raw" 2>&1 || rc=$?
if [ "$rc" -ne 0 ]; then
  golive_finish FAIL "make-env.sh exited $rc (raw output in $(basename "$raw"))"
fi
rc=0
docker compose -f "$GOLIVE_ROOT/infra/local/compose.yaml" up -d --wait >> "$raw" 2>&1 || rc=$?
if [ "$rc" -ne 0 ]; then
  golive_finish FAIL "docker compose up --wait exited $rc (raw output in $(basename "$raw"))"
fi

running="$(docker compose -f "$GOLIVE_ROOT/infra/local/compose.yaml" ps --status running -q | wc -l | tr -d ' ')"
if ! golive_port_in_use "$SELLBIRD_LOCAL_PG_PORT"; then
  golive_finish FAIL "stand-in is up ($running containers running) but Postgres does not accept connections on its published port"
fi
if [ "$running" -lt 3 ]; then
  golive_finish FAIL "only $running stand-in containers are running (expected at least postgres, kratos, flint-gate)"
fi
golive_finish PASS "stand-in up: $running containers running; ports pg=$SELLBIRD_LOCAL_PG_PORT gate=$SELLBIRD_LOCAL_GATE_PORT direct=$SELLBIRD_LOCAL_DIRECT_PORT"
