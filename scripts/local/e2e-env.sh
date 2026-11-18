#!/usr/bin/env bash
# Run a command with the gateway e2e test's environment from infra/local/.env.
#
#   SELLBIRD_GATEWAY_URL=http://localhost:4456 \
#     scripts/local/e2e-env.sh .venv/bin/python -m pytest -q tests/test_gateway_mode_e2e.py
#
# Exports every SELLBIRD_E2E_* variable make-env.sh wrote (see
# openspec/changes/hosted-gateway-mode/design.md, "E2E environment interface")
# and SELLBIRD_GATEWAY_URL (default http://localhost:4456 when unset), then
# execs the command. It exports nothing else: in particular never
# SELLBIRD_DASHBOARD_MODE, which lives only inside the Sellbird container.
# Values are never printed.
set -euo pipefail
# shellcheck source=scripts/local/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

[[ $# -gt 0 ]] || sb_die "usage: e2e-env.sh <command> [args...]"

for key in SELLBIRD_E2E_HOST SELLBIRD_E2E_ALLOWED_SUB SELLBIRD_E2E_SESSION_COOKIE \
           SELLBIRD_E2E_OTHER_SESSION_COOKIE SELLBIRD_E2E_DIRECT_URL \
           SELLBIRD_E2E_PUBLIC_HOST SELLBIRD_E2E_GATE_KEY_FILE \
           SELLBIRD_E2E_GATE_KID SELLBIRD_E2E_GATE_ISSUER; do
  value="$(sb_env_get "$key")"
  export "$key=$value"
done
export SELLBIRD_GATEWAY_URL="${SELLBIRD_GATEWAY_URL:-http://localhost:4456}"
unset SELLBIRD_DASHBOARD_MODE

exec "$@"
