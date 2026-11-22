#!/usr/bin/env bash
# SCN-LIVE-003 negative control: on the LOCAL Postgres stand-in only (never the cluster, no kubectl),
# the project's own sending-safety tests, which drain the outbox through the recording test
# transport (FakeProvider: nothing leaves the machine), show that the sent count moves exactly
# when an item is approved and due:
#   tests/test_outbox_native.py::test_stage_campaign_renders_and_respects_approval  (nothing sent before approval)
#   tests/test_outbox_native.py::test_drain_sends_approved_due_items               (approved + due -> recorded as sent)
#   tests/test_send_safety_parity.py scenarios approval_ladder and under_daily_limit, on sqlite and
#   postgres (the one approved item is the only one sent; the unapproved one is not)
# Selected with -k on those names; all selected tests must pass with zero skips (a skipped postgres
# variant would mean the stand-in was not used). Packet:  neg-approved-send.sh SCN-LIVE-003
# Refuses to run if SELLBIRD_DATABASE_URL or SELLBIRD_MIGRATE_DATABASE_URL is set in the environment
# (they could name a live database) or if the stand-in's DSN host is not loopback; GOLIVE_KUBE_CONTEXT
# and KUBECONFIG are removed from the tests' environment. The live pause is untouched.
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin negativeControl SCN-LIVE-003
cd "$GOLIVE_ROOT"

if [ -n "${SELLBIRD_DATABASE_URL:-}" ] || [ -n "${SELLBIRD_MIGRATE_DATABASE_URL:-}" ]; then
  golive_finish BLOCKED "SELLBIRD_DATABASE_URL or SELLBIRD_MIGRATE_DATABASE_URL is set in the environment; unset it: this control runs on the local stand-in only"
fi
golive_require_venv pytest pytest_asyncio psycopg
golive_load_ports
if ! golive_pg_dsns_export; then
  golive_finish BLOCKED "the local stand-in is not prepared (no infra/local/.env): run standin-up.sh first"
fi
case "$SELLBIRD_TEST_PG_APP_DSN" in
  *"@127.0.0.1:"* | *"@localhost:"*) ;;
  *) golive_finish BLOCKED "the stand-in DSN does not point at loopback; refusing" ;;
esac

xml="$(golive_artifact neg-approved-send-junit.xml)"
raw="$(golive_artifact raw-neg-approved-send.log)"
rc=0
"${GOLIVE_CLEAN_ENV[@]}" env -u GOLIVE_KUBE_CONTEXT -u KUBECONFIG "$GOLIVE_PY" -m pytest -q -rs -p no:cacheprovider \
  --junitxml="$xml" tests/test_outbox_native.py tests/test_send_safety_parity.py \
  -k "test_stage_campaign_renders_and_respects_approval or test_drain_sends_approved_due_items or approval_ladder or under_daily_limit" \
  >> "$raw" 2>&1 || rc=$?
if [ ! -s "$xml" ]; then
  golive_finish FAIL "pytest produced no junit file (exit $rc)"
fi
c="$("$GOLIVE_PY" -I "$GOLIVE_DIR/_junit.py" counts "$xml")"
golive_note "selected tests: $c"
tests="$(jq -r '.tests' <<< "$c")"
passed="$(jq -r '.passed' <<< "$c")"
if [ "$rc" -ne 0 ] || [ "$tests" -lt 6 ] || [ "$passed" -ne "$tests" ]; then
  golive_finish FAIL "the sending-safety tests did not all pass (exit $rc, $c; at least 6 expected: 2 outbox tests + 2 scenarios x 2 backends)"
fi
golive_finish PASS "on the local stand-in the test transport recorded exactly the approved, due item as sent ($c); the live pause is untouched"
