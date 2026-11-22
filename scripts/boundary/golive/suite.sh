#!/usr/bin/env bash
# SCN-REG-001: the full pytest suite is green AND every required new test ID was collected and
# passed. Packet command `scn-suite`:  bash scripts/boundary/golive/suite.sh SCN-REG-001
#
# Method: one `pytest --junitxml` run of the whole suite, through scripts/local/e2e-env.sh so the
# gateway e2e tests see the stand-in's variables, with the stand-in's Postgres DSNs exported (never
# printed) so the Postgres variants run instead of skipping. _junit.py then looks every ID in
# fixtures/golive-required-tests.txt up in the junit file: it must match at least one test and
# every match must have PASSED (a skip is not a pass). Counts and IDs only are printed.
# Needs the stand-in (standin-up.sh) and node (the UI tests skip without it).
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin scenario SCN-REG-001
GOLIVE_TREE_BEFORE=""  # the suite may legitimately leave ignored caches; the tree guard does not apply
cd "$GOLIVE_ROOT"

golive_require_tools node
golive_require_venv pytest pytest_asyncio psycopg yaml
if [ ! -f "$GOLIVE_FIXTURE" ]; then
  golive_finish BLOCKED "fixtures/golive-required-tests.txt is missing"
fi
golive_load_ports
if ! golive_pg_dsns_export; then
  golive_finish BLOCKED "the local stand-in is not prepared (no infra/local/.env): run standin-up.sh first"
fi
printf '%s\n' "$(golive_sha256 "$GOLIVE_FIXTURE")" > "$(golive_artifact fixture.sha256)"

xml="$(golive_artifact suite-junit.xml)"
raw="$(golive_artifact raw-suite-pytest.log)"
rc=0
"${GOLIVE_CLEAN_ENV[@]}" bash "$GOLIVE_ROOT/scripts/local/e2e-env.sh" \
  "$GOLIVE_PY" -m pytest -q -rs -p no:cacheprovider --junitxml="$xml" >> "$raw" 2>&1 || rc=$?
golive_note "pytest exit code $rc"
if [ ! -s "$xml" ]; then
  golive_finish FAIL "pytest produced no junit file (exit $rc); see $(basename "$raw")"
fi
c="$("$GOLIVE_PY" -I "$GOLIVE_DIR/_junit.py" counts "$xml")"
golive_note "counts: $c"
req_out="$(golive_artifact suite-required.txt)"
req_rc=0
"$GOLIVE_PY" -I "$GOLIVE_DIR/_junit.py" required "$xml" "$GOLIVE_FIXTURE" --root "$GOLIVE_ROOT" --expect pass > "$req_out" 2>&1 || req_rc=$?
grep -v ' OK ' "$req_out" | tail -n 40 || true
if [ "$rc" -ne 0 ]; then
  golive_finish FAIL "pytest exited $rc; counts $c"
fi
if [ "$req_rc" -ne 0 ]; then
  golive_finish FAIL "required test IDs not all collected and passed (see suite-required.txt); counts $c"
fi
golive_finish PASS "zero failures; every required test ID collected and passed; counts $c"
