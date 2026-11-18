#!/usr/bin/env bash
# Negative controls for the postgres-gke-deployment boundary packet.
#
#   scripts/boundary/negative_controls.sh <SCENARIO-ID>
#
# Each control plants the bad input its scenario names, runs the check, and
# passes only when the expected refusal is observed (a refusal for another
# reason is a FAIL). The last line is always
#
#   NEGATIVE-CONTROL <ID> PASS|FAIL|BLOCKED: <reason>
#
# Exit status: 0 PASS, 1 FAIL (the bad input was accepted, or refused for the
# wrong reason), 2 BLOCKED (a prerequisite is missing: docker, the Postgres
# stand-in, the gateway, a venv), 64 unknown scenario or usage.
#
# Bad inputs are planted in scratch copies (a copy of the working tree, scratch
# git repositories, a copy of one document); the checkout is compared before
# and after and any change fails the control. No connection string, token or
# key is printed. Postgres controls use the local stand-in's DSNs
# (scripts/local/dsn.sh); gateway controls need it up on localhost:4456.
set -euo pipefail

# shellcheck source=scripts/boundary/lib_negative.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib_negative.sh"

SCENARIOS="SCN-BASE-001 SCN-STORE-001 SCN-STORE-002 SCN-STORE-003 SCN-SEND-001 SCN-SEND-002
SCN-MOVE-001 SCN-AUTH-001 SCN-AUTH-002 SCN-LOG-001 SCN-BRAIN-001 SCN-SHIP-001 SCN-CONTRACT-001"

usage() { printf 'usage: %s <SCENARIO-ID>\n  one of: %s\n' "$0" "$(echo $SCENARIOS)" >&2; exit 64; }

# nc_run_pytest <tree> <pytest args...>: pytest in a scratch tree; sets OUT and RC.
nc_run_pytest() {
  local tree="$1"; shift
  RC=0
  OUT="$(cd "$tree" && COLUMNS=300 "${NC_CLEAN_ENV[@]}" PYTHONPATH="$tree${NC_EXTRA_PATH:+:$NC_EXTRA_PATH}" \
        "$PY" -m pytest -p no:cacheprovider -q --tb=short "$@" 2>&1)" || RC=$?
}

# ── SCN-BASE-001: quadratic scans must trip both timing tests ──
scn_base_001() {
  nc_need_python
  nc_scratch_tree; local tree="$NC_DIR"
  nc_scratch; local plug="$NC_DIR"
  cat >"$plug/negctl_quadratic.py" <<'PLUGIN'
"""Pytest plugin: makes the testimonial and reply scans quadratic (K * n * n/step)."""
import os

os.environ.pop("SELLBIRD_HOME", None)


def _burn(size, step, times=1):
    hay = "a" * size
    for _ in range(times):
        for start in range(0, size, step):
            hay.find("\0", start)  # a full scan of the rest of the text, per step


def pytest_configure(config):
    from sellbird.agents import handler
    from sellbird.collectors import people

    drop_quoted, find_people, opt_out = people.drop_quoted, people.find_people, handler._opt_out_reason

    def slow_drop_quoted(html):
        _burn(len(html), 1, 10)
        return drop_quoted(html)

    def slow_find_people(pages, *args, **kwargs):
        _burn(sum(len(h) for _, h in pages), 1, 10)
        return find_people(pages, *args, **kwargs)

    def slow_opt_out(their_text, own_words):
        _burn(len(their_text), 4)
        return opt_out(their_text, own_words)

    people.drop_quoted, people.find_people, handler._opt_out_reason = (
        slow_drop_quoted, slow_find_people, slow_opt_out)
PLUGIN
  NC_EXTRA_PATH="$plug" nc_run_pytest "$tree" -p negctl_quadratic -rf \
    tests/test_people_finder.py::test_nested_testimonials_are_bounded \
    tests/test_compliance_footer.py::test_a_long_french_reply_is_quick
  local name hits
  for name in test_nested_testimonials_are_bounded test_a_long_french_reply_is_quick; do
    grep -Eq "^FAILED .*::$name( |$)" <<<"$OUT" || { nc_tail "$OUT" >&2; verdict FAIL "$name did not fail against the quadratic scans (exit $RC)"; }
  done
  hits="$(grep -Ec 'took x[0-9.]+ longer \(limit x' <<<"$OUT" || true)"
  [[ "$hits" -ge 2 ]] || { nc_tail "$OUT" >&2; verdict FAIL "tests failed, but not on the growth-ratio assertion"; }
  verdict PASS "both timing tests fail on the growth ratio against planted quadratic scans"
}

# ── SCN-STORE-001: divergent company dedup must fail the storage contract ──
scn_store_001() {
  nc_need_python
  nc_scratch_tree dedup; local tree="$NC_DIR" test=test_a_company_is_recorded_once_per_normalised_domain
  OUT="" RC=0
  OUT="$(cd "$tree" && COLUMNS=300 "${NC_CLEAN_ENV[@]}" -u SELLBIRD_TEST_PG_MIGRATE_DSN -u SELLBIRD_TEST_PG_APP_DSN \
        PYTHONPATH="$tree" "$PY" -m pytest -p no:cacheprovider -q --tb=short -rf \
        "tests/storage_contract/test_contract.py::$test" 2>&1)" || RC=$?
  grep -Eq "^FAILED .*::$test\[sqlite\]" <<<"$OUT" \
    || { nc_tail "$OUT" >&2; verdict FAIL "the contract did not fail on $test with the planted dedup divergence (exit $RC)"; }
  grep -q 'AssertionError' <<<"$OUT" || { nc_tail "$OUT" >&2; verdict FAIL "$test failed, but not on its assertion"; }
  verdict PASS "contract test $test (company dedup, add_company) fails with the domain no longer normalised"
}

scn_store_002() { nc_need_python; nc_load_pg; nc_probe store002; }
scn_store_003() { nc_need_python; nc_load_pg; nc_probe store003; }
scn_send_001() { nc_need_python; nc_load_pg; nc_probe send001; }
scn_move_001() { nc_need_python; nc_load_pg; nc_probe move001; }
scn_auth_002() { nc_need_python; nc_probe auth002; }

# ── SCN-SEND-002: quiet hours, daily limit, suppressed address, unapproved item ──
scn_send_002() {
  nc_need_python; nc_load_pg
  nc_scratch_tree; local tree="$NC_DIR"
  nc_run_pytest "$tree" -rs tests/test_send_safety_parity.py -k \
    '(daily_limit and not under_daily_limit) or suppressed_address or quiet_hours_hold_replies or approval_ladder'
  if [[ "$RC" -eq 0 ]] && grep -Eq '(^| )8 passed( |,)' <<<"$OUT" && ! grep -Eq '[0-9]+ (skipped|failed|errors?)' <<<"$OUT"; then
    verdict PASS "daily limit, suppressed address, quiet hours and unapproved item each refused on sqlite and postgres (8 cases)"
  fi
  nc_tail "$OUT" >&2
  verdict FAIL "the four refusal scenarios did not all pass on both backends (exit $RC)"
}

# ── SCN-AUTH-001: forged header, wrong aud, expired, non-allowlisted: 401, no data ──
scn_auth_001() {
  nc_need_python
  local url="${SELLBIRD_GATEWAY_URL:-http://localhost:4456}" t=tests/test_gateway_mode_e2e.py
  [[ -f "$NC_ROOT/infra/local/.env" ]] || verdict BLOCKED "infra/local/.env missing (run scripts/local/make-env.sh)"
  command -v curl >/dev/null 2>&1 || verdict BLOCKED "curl is required to probe the gateway"
  curl -s -o /dev/null --max-time 5 "$url/" || verdict BLOCKED "no gateway at $url (bring the local stand-in up)"
  RC=0
  OUT="$(cd "$NC_ROOT" && COLUMNS=300 SELLBIRD_GATEWAY_URL="$url" PYTHONPATH="$NC_ROOT" \
        scripts/local/e2e-env.sh "$PY" -m pytest -p no:cacheprovider -q --tb=line -rs \
        "$t::test_allowlisted_session_resolves_to_the_allowlisted_identity" \
        "$t::test_direct_positive_control" \
        "$t::test_forged_identity_header_without_a_session_is_refused" \
        "$t::test_non_allowlisted_identity_is_refused" \
        "$t::test_direct_forged_identity_header_is_refused" \
        "$t::test_direct_wrong_audience_is_refused" \
        "$t::test_direct_expired_token_is_refused" \
        "$t::test_direct_non_allowlisted_identity_is_refused" 2>&1)" || RC=$?
  if [[ "$RC" -eq 0 ]] && grep -Eq '(^| )8 passed( |,)' <<<"$OUT" && ! grep -Eq '[0-9]+ (skipped|failed|errors?)' <<<"$OUT"; then
    verdict PASS "forged header, wrong audience, expired token and non-allowlisted identity each 401 with no data; both positive controls 200"
  fi
  nc_tail "$OUT" >&2
  verdict FAIL "the refusal tests did not all pass against the gateway (exit $RC)"
}

# ── SCN-LOG-001: an image that prints the token must fail the log search ──
scn_log_001() {
  nc_need_docker
  nc_scratch_tree log; local tree="$NC_DIR" tag="sellbird:negctl-log-$$" out rc=0
  NC_DOCKER_IMAGES+=("$tag")
  out="$(docker build -q -t "$tag" "$tree" 2>&1)" || { nc_tail "$out" >&2; verdict BLOCKED "the planted image did not build"; }
  out="$(bash "$NC_ROOT/scripts/boundary/check_container.sh" "$tag" 2>&1)" || rc=$?
  case "$rc" in
    0) verdict FAIL "check_container.sh passed an image that prints the dashboard token" ;;
    2) nc_tail "$out" >&2; verdict BLOCKED "check_container.sh could not run" ;;
  esac
  if grep -Eq '^FAIL  (dashboard token appears in local-mode logs|an unlock link appears in local-mode logs)' <<<"$out"; then
    verdict PASS "check_container.sh fails on the log search (token or unlock link in local-mode logs)"
  fi
  nc_tail "$out" >&2
  verdict FAIL "check_container.sh failed, but not on the log search"
}

# ── SCN-BRAIN-001: no CLAUDE_CODE_OAUTH_TOKEN: the documented error, no file fallback ──
scn_brain_001() {
  nc_need_docker
  local image="${NEGCTL_IMAGE:-sellbird:boundary}" out src
  docker image inspect "$image" >/dev/null 2>&1 || verdict BLOCKED "no local image $image (build it, or set NEGCTL_IMAGE)"
  src="$(cat <<'PYSRC'
import asyncio, logging, os, sys
assert "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
from sellbird.brain import Brain
from sellbird.state import StateManager
async def main():
    state = StateManager("/tmp/brain-check.db")
    await state.init_db()
    reply = await Brain(state).think("negative control", agent="boundary", task="check", max_retries=0)
    print("BRAIN_REPLY_EMPTY=" + str(reply == ""))
    conf = os.environ.get("CLAUDE_CONFIG_DIR", "")
    found = [os.path.join(d, f) for base in ("/data", os.path.expanduser("~"), conf) if base
             for d, _, files in os.walk(base) for f in files if f == ".credentials.json"]
    print("CREDENTIAL_FILES=" + str(len(found)))
asyncio.run(main())
PYSRC
)"
  out="$(docker run --rm --read-only --tmpfs /tmp:rw,nosuid,nodev,exec,size=512m \
          --tmpfs /data:rw,nosuid,nodev,mode=1777 --cap-drop ALL --security-opt no-new-privileges \
          --network none --entrypoint python "$image" -c "$src" 2>&1 || true)"
  grep -qF 'Non-retryable Claude error (auth)' <<<"$out" \
    || { nc_tail "$out" >&2; verdict FAIL "no documented missing-login error with the token unset"; }
  grep -qx 'BRAIN_REPLY_EMPTY=True' <<<"$out" || { nc_tail "$out" >&2; verdict FAIL "the brain returned a reply without a login"; }
  grep -qx 'CREDENTIAL_FILES=0' <<<"$out" || { nc_tail "$out" >&2; verdict FAIL "a credential file exists to fall back to"; }
  verdict PASS "token unset: 'Non-retryable Claude error (auth)', empty reply, no credential file"
}

# ── SCN-SHIP-001: tag-only image, backwards pin, malformed digest ──
scn_ship_001() {
  command -v git >/dev/null 2>&1 || verdict BLOCKED "git is required"
  nc_scratch; local w="$NC_DIR" src="$NC_DIR/source" ovl="$NC_DIR/overlay" i d2 d3 file
  export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null GIT_AUTHOR_NAME=negctl \
    GIT_AUTHOR_EMAIL=negctl@example.test GIT_COMMITTER_NAME=negctl GIT_COMMITTER_EMAIL=negctl@example.test
  file="apps/sellbird/overlays/production/kustomization.yaml"
  mkdir -p "$src" "$ovl/$(dirname "$file")"
  git -C "$src" init -q || verdict BLOCKED "cannot create a scratch git repository"
  local -a sha=()
  for i in 1 2 3; do
    echo "$i" >"$src/f"
    git -C "$src" add f && git -C "$src" commit -q -m "c$i" || verdict BLOCKED "cannot commit in the scratch repository"
    sha+=("$(git -C "$src" rev-parse HEAD)")
  done
  d2="sha256:$(printf '%064d' 0 | tr 0 b)"; d3="sha256:$(printf '%064d' 0 | tr 0 c)"
  printf '%s\n' 'apiVersion: kustomize.config.k8s.io/v1beta1' 'kind: Kustomization' 'images:' \
    '  - name: sellbird' '    newName: ghcr.io/example-owner/sellbird' "    newTag: \"${sha[1]}\"" \
    "    digest: $d2" >"$ovl/$file"
  git -C "$ovl" init -q && git -C "$ovl" add -A && git -C "$ovl" commit -q -m overlay \
    || verdict BLOCKED "cannot create the scratch overlay repository"
  cp -R "$ovl" "$w/overlay-ok"

  pin() { local repo="$1"; shift; bash "$NC_ROOT/scripts/deploy/pin_overlay.sh" --overlay-repo "$repo" --source-repo "$src" "$@" 2>&1; }
  state() { printf '%s %s %s' "$(git -C "$ovl" rev-parse HEAD)" "$(git -C "$ovl" status --porcelain | cksum)" "$(git hash-object "$ovl/$file")"; }
  refused() {  # <label> <phrase> <pin args...>
    local label="$1" phrase="$2" before out rc=0; shift 2
    before="$(state)"
    out="$(pin "$ovl" "$@")" || rc=$?
    [[ "$rc" -eq 1 ]] || verdict FAIL "$label: expected exit 1 (refused), got $rc"
    grep -qF "$phrase" <<<"$out" || { nc_tail "$out" >&2; verdict FAIL "$label: refused, but not for the expected reason"; }
    [[ "$(state)" == "$before" ]] || verdict FAIL "$label: the scratch overlay changed although the pin was refused"
  }

  out="$(pin "$w/overlay-ok" --tag "${sha[2]}" --digest "$d3" --image ghcr.io/example-owner/sellbird)" \
    || { nc_tail "$out" >&2; verdict FAIL "positive control: a valid forward pin was refused"; }
  refused "tag-only image" "no digest given" --tag "${sha[2]}"
  refused "backwards pin" "backwards" --tag "${sha[0]}" --digest "$d3"
  refused "malformed digest" "digest is not sha256" --tag "${sha[2]}" --digest "sha256:$(printf '%063d' 0)"
  verdict PASS "tag-only, backwards and malformed-digest pins each refused (exit 1, stated reason, overlay unchanged); a forward pin is accepted"
}

# ── SCN-CONTRACT-001: the document without its JWKS section must fail, naming it ──
scn_contract_001() {
  local doc="$NC_ROOT/docs/platform-interface.md" section="## Issuer and JWKS" out rc=0 copy
  [[ -f "$doc" ]] || verdict BLOCKED "docs/platform-interface.md is missing"
  grep -Fxq "$section" "$doc" || verdict BLOCKED "the document has no '$section' section to remove"
  nc_scratch; copy="$NC_DIR/platform-interface.md"
  awk -v h="$section" '$0 == h { skip = 1; next } skip && /^## / { skip = 0 } !skip { print }' "$doc" >"$copy"
  ! grep -Fxq "$section" "$copy" || verdict BLOCKED "could not remove the section from the copy"
  out="$(bash "$NC_ROOT/scripts/boundary/check_platform_contract.sh" "$copy" 2>&1)" || rc=$?
  [[ "$rc" -eq 1 ]] || { nc_tail "$out" >&2; verdict FAIL "check_platform_contract.sh exited $rc on a document without its JWKS section"; }
  grep -Fq "MISSING: section 'Issuer and JWKS'" <<<"$out" \
    || { nc_tail "$out" >&2; verdict FAIL "the check failed but did not name the missing section"; }
  verdict PASS "check_platform_contract.sh exits 1 and names the missing section 'Issuer and JWKS'"
}

NC_ID="${1:-}"
[[ $# -eq 1 ]] || usage
case " $(echo $SCENARIOS) " in *" $NC_ID "*) ;; *) usage ;; esac
NC_TREE_BEFORE="$(nc_tree_state)"
"scn_$(printf '%s' "${NC_ID#SCN-}" | tr 'A-Z-' 'a-z_')"
verdict FAIL "scenario function returned without a verdict"
