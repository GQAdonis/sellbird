#!/usr/bin/env bash
# Create the two Kratos identities the local stand-in needs, through the Kratos
# admin API, which is reachable only on the compose network (never published).
#
#   operator@example.test  the allowlisted operator (its id becomes
#                          SELLBIRD_GATE_ALLOWED_SUBS and SELLBIRD_E2E_ALLOWED_SUB)
#   other@example.test     a second, active identity that is NOT allowlisted
#
# Usage (run by scripts/local/make-env.sh after Kratos is healthy):
#
#   SELLBIRD_LOCAL_OPERATOR_PASSWORD=... SELLBIRD_LOCAL_OTHER_PASSWORD=... \
#     infra/kratos/create-identities.sh
#
# Prints exactly two lines on stdout and nothing secret:
#
#   OPERATOR_ID=<uuid>
#   OTHER_ID=<uuid>
#
# Kratos assigns identity ids itself: its admin create body has no `id` field,
# so the contract's placeholder 00000000-0000-4000-8000-000000000001 cannot be
# forced. The generated id is written into the uncommitted .env instead.
#
# Passwords are read from the environment and sent on stdin, never on a command
# line. Each identity is created with a password credential only; TOTP is
# enrolled afterwards through the self-service settings flow
# (scripts/local/kratos_session.py), exactly as a person would.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/infra/local/compose.yaml")
PYTHON="${PYTHON:-python3}"

: "${SELLBIRD_LOCAL_OPERATOR_PASSWORD:?must be set (see scripts/local/make-env.sh)}"
: "${SELLBIRD_LOCAL_OTHER_PASSWORD:?must be set (see scripts/local/make-env.sh)}"

# admin_post <path>: POST the JSON on stdin to the Kratos admin API from a
# throwaway curl container on the compose network; the response is on stdout.
admin_post() {
  "${COMPOSE[@]}" --profile tools run --rm --no-deps -T kratos-admin-client \
    --silent --show-error --fail-with-body --max-time 20 \
    -X POST "http://kratos:4434$1" \
    -H 'Content-Type: application/json' -H 'Accept: application/json' \
    --data-binary @-
}

# identity_body <email> <password-env-var>: the createIdentity JSON on stdout.
identity_body() {
  EMAIL="$1" PW_VAR="$2" "$PYTHON" -I -c '
import json, os
print(json.dumps({
    "schema_id": "sellbird",
    "state": "active",
    "traits": {"email": os.environ["EMAIL"]},
    "credentials": {"password": {"config": {"password": os.environ[os.environ["PW_VAR"]]}}},
}))'
}

# id_from_response: the identity id from a createIdentity response on stdin.
id_from_response() {
  "$PYTHON" -I -c '
import json, sys, uuid
print(uuid.UUID(json.load(sys.stdin)["id"]))'
}

create() {
  identity_body "$1" "$2" | admin_post /admin/identities | id_from_response
}

operator_id="$(create operator@example.test SELLBIRD_LOCAL_OPERATOR_PASSWORD)"
other_id="$(create other@example.test SELLBIRD_LOCAL_OTHER_PASSWORD)"

printf 'OPERATOR_ID=%s\nOTHER_ID=%s\n' "$operator_id" "$other_id"
