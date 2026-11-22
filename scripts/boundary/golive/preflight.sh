#!/usr/bin/env bash
# Boundary preflight (packet command `preflight`). Checks every tool, login, port and input the
# later golive scripts use, so a missing prerequisite fails here, in one line each, and not in
# the middle of the run. It also creates this attempt's evidence folder (a new dated folder
# under evidence/boundary-run/, or $EVIDENCE_DIR if set) and writes ports.env and run-info.json.
#
#   bash scripts/boundary/golive/preflight.sh
#
# Environment: GOLIVE_KUBE_CONTEXT (no default; unset means the live scripts record BLOCKED),
# GOLIVE_REQUIRE_LIVE=1 (make an unset context a failure here), GOLIVE_BASE_REF (the pre-phase
# commit for neg-reg.sh; default merge-base of HEAD and origin/main), GOLIVE_ALLOW_DIRTY=1.
# Prints no env value, no account name, no URL.
set -euo pipefail
export GOLIVE_NEW_EVIDENCE=1
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin support PREFLIGHT
cd "$GOLIVE_ROOT"

FAILS=0
pf_fail() {
  printf 'MISSING: %s\n' "$*"
  FAILS=$((FAILS + 1))
}
pf_ok() { printf 'ok: %s\n' "$*"; }

# --- tools ---------------------------------------------------------------------------------
for t in docker jq gh git kubectl uv node openssl awk; do
  if golive_have "$t"; then
    pf_ok "$t found"
  else
    pf_fail "$t is not installed"
  fi
done
if ! golive_have sha256sum && ! golive_have shasum; then
  pf_fail "neither sha256sum nor shasum is installed"
fi
if golive_have kustomize || { golive_have kubectl && kubectl kustomize --help > /dev/null 2>&1; }; then
  pf_ok "a kustomize renderer is available (kustomize or kubectl kustomize)"
elif golive_have docker; then
  pf_ok "no local kustomize; the pinned kustomize image will be used (needs a pull)"
else
  pf_fail "no way to render kustomize (install kustomize, or kubectl with kustomize)"
fi
if golive_have docker; then
  if docker info > /dev/null 2>&1; then
    pf_ok "docker daemon reachable"
  else
    pf_fail "docker is installed but the daemon is not reachable"
  fi
  docker compose version > /dev/null 2>&1 && pf_ok "docker compose v2" || pf_fail "docker compose v2 is missing"
  docker buildx version > /dev/null 2>&1 && pf_ok "docker buildx (BuildKit)" || pf_fail "docker buildx is missing (the Dockerfile needs BuildKit)"
fi

# --- venv and the YAML parser ------------------------------------------------------------------
if [ ! -x "$GOLIVE_PY" ]; then
  pf_fail ".venv/bin/python is missing: create it with uv venv && uv pip install -e '.[dev,postgres,hosted]'"
else
  mods="yaml psycopg jwt pytest pytest_asyncio fastapi aiosqlite"
  miss=""
  for m in $mods; do
    "$GOLIVE_PY" -I -c "import $m" > /dev/null 2>&1 || miss="$miss $m"
  done
  if [ -n "$miss" ]; then
    pf_fail ".venv lacks python modules:$miss (run: uv pip install -e '.[dev,postgres,hosted]')"
  else
    pf_ok ".venv has PyYAML and the postgres, hosted and dev extras"
  fi
fi

# --- uv at the version the lock scripts pin ----------------------------------------------------------
if golive_have uv; then
  want="$(tr -d '[:space:]' < scripts/ci/uv-version)"
  have="$(uv --version | awk '{print $2}')"
  if [ "$have" = "$want" ]; then
    pf_ok "uv $have matches scripts/ci/uv-version"
  else
    pf_fail "uv $have found; scripts/ci/check-lock-fresh.sh needs exactly $want (install that version)"
  fi
fi

# --- inputs a human must have produced -----------------------------------------------------------------
if [ ! -f requirements.lock ] || ! grep -q -- '--hash=sha256:' requirements.lock; then
  pf_fail "requirements.lock is missing or has no hashes: a human must run scripts/ci/lock-requirements.sh (uv $(tr -d '[:space:]' < scripts/ci/uv-version), network) and commit the result"
else
  pf_ok "requirements.lock present with hashes"
fi
if grep -Eq '^[[:space:]]+SCANNER_TRIVY_SHA256_LINUX_64BIT:[[:space:]]*[0-9a-f]{64}[[:space:]]*$' .github/workflows/images.yml; then
  pf_ok "images.yml pins a 64-hex Trivy checksum"
else
  pf_fail "images.yml SCANNER_TRIVY_SHA256_LINUX_64BIT is not 64 lowercase hex: a human must copy the Linux-64bit tarball's SHA-256 from the official checksums file of that Trivy version into the workflow"
fi
if [ ! -f "$GOLIVE_FIXTURE" ]; then
  pf_fail "fixtures/golive-required-tests.txt is missing"
else
  bad=0
  while IFS= read -r line; do
    case "$line" in '' | '#'*) continue ;; esac
    f="${line%%::*}"
    if [ ! -f "$GOLIVE_ROOT/$f" ]; then
      bad=$((bad + 1))
    fi
  done < "$GOLIVE_FIXTURE"
  if [ "$bad" -eq 0 ]; then
    pf_ok "every required test file in the fixture exists"
  else
    pf_fail "$bad required test IDs name a file that does not exist"
  fi
fi

# --- git: clean relevant paths, a base commit, the remote ------------------------------------------------
dirty="$(golive_relevant_dirty | wc -l | tr -d ' ')"
if [ "$dirty" -gt 0 ] && [ -z "${GOLIVE_ALLOW_DIRTY:-}" ]; then
  pf_fail "$dirty modified or untracked paths under tests, sellbird, infra, .github, scripts and the build inputs: commit them first (the scratch worktrees and CI only see commits); GOLIVE_ALLOW_DIRTY=1 overrides"
else
  pf_ok "relevant paths are committed ($dirty dirty, override=${GOLIVE_ALLOW_DIRTY:-no})"
fi
base=""
if base="$(golive_base_sha)"; then
  pf_ok "base commit for neg-reg.sh resolved"
else
  base=""
  pf_fail "no usable base commit: origin/main is missing or equals HEAD; set GOLIVE_BASE_REF to the pre-phase commit"
fi
git remote get-url origin > /dev/null 2>&1 && pf_ok "git remote origin exists" || pf_fail "git remote origin is missing"

# --- gh login ---------------------------------------------------------------------------------------------
if golive_have gh; then
  if gh auth status > /dev/null 2>&1; then
    pf_ok "gh is logged in"
  else
    pf_fail "gh is not logged in: the operator must run gh auth login"
  fi
fi

# --- kube context (never guessed) ----------------------------------------------------------------------------
if [ -z "${GOLIVE_KUBE_CONTEXT:-}" ]; then
  if [ -n "${GOLIVE_REQUIRE_LIVE:-}" ]; then
    pf_fail "GOLIVE_KUBE_CONTEXT is not set (GOLIVE_REQUIRE_LIVE=1)"
  else
    printf 'note: GOLIVE_KUBE_CONTEXT is not set; live-*.sh will record BLOCKED\n'
  fi
elif golive_have kubectl; then
  ctxs="$(kubectl config get-contexts -o name 2> /dev/null || true)"
  nl=$'\n'
  case "$nl$ctxs$nl" in
    *"$nl$GOLIVE_KUBE_CONTEXT$nl"*) pf_ok "GOLIVE_KUBE_CONTEXT names a context in the kubeconfig" ;;
    *) pf_fail "GOLIVE_KUBE_CONTEXT does not name a context in the kubeconfig" ;;
  esac
fi

# --- ports (chosen free, exported through ports.env) --------------------------------------------------------------
pg="$(golive_free_port "${SELLBIRD_LOCAL_PG_PORT:-55432}")" || pg=""
gate="$(golive_free_port "${SELLBIRD_LOCAL_GATE_PORT:-4456}")" || gate=""
direct="$(golive_free_port "${SELLBIRD_LOCAL_DIRECT_PORT:-5555}")" || direct=""
if [ -z "$pg" ] || [ -z "$gate" ] || [ -z "$direct" ]; then
  pf_fail "could not find free host ports for the stand-in"
else
  printf 'SELLBIRD_LOCAL_PG_PORT=%s\nSELLBIRD_LOCAL_GATE_PORT=%s\nSELLBIRD_LOCAL_DIRECT_PORT=%s\n' "$pg" "$gate" "$direct" > "$EVIDENCE_DIR/ports.env"
  pf_ok "stand-in ports chosen: postgres $pg, gate $gate, direct $direct (ports.env)"
fi

# --- run info ---------------------------------------------------------------------------------------------------------
jq -nc --arg commit "$(git rev-parse HEAD)" --arg base "$base" \
  --arg fixture_sha256 "$([ -f "$GOLIVE_FIXTURE" ] && golive_sha256 "$GOLIVE_FIXTURE" || echo none)" \
  --arg docker "$(docker --version 2> /dev/null | awk '{print $3}' | tr -d ',' || true)" \
  --arg uv "$(uv --version 2> /dev/null | awk '{print $2}' || true)" \
  --arg started "$(golive_now_iso)" \
  '{commit: $commit, base: $base, fixture_sha256: $fixture_sha256, docker: $docker, uv: $uv, started: $started}' \
  > "$EVIDENCE_DIR/run-info.json"

printf 'evidence folder: %s\n' "${EVIDENCE_DIR#"$GOLIVE_ROOT"/}"
printf 'next: export EVIDENCE_DIR=%s (other scripts also find it through the pointer file)\n' "${EVIDENCE_DIR#"$GOLIVE_ROOT"/}"
if [ "$FAILS" -gt 0 ]; then
  golive_finish FAIL "$FAILS prerequisite(s) missing (see MISSING lines above)"
fi
golive_finish PASS "all prerequisites present"
