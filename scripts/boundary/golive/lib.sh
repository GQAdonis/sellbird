# Shared helpers for scripts/boundary/golive/*.sh (OpenSpec change go-live-boundary).
# Source it; do not execute it.
# shellcheck shell=bash
#
# Conventions every script follows:
#   - `set -euo pipefail`, then `source lib.sh`, then `golive_begin <kind> <scenario-ids>`.
#   - It ends with `golive_finish <PASS|FAIL|BLOCKED|NOT_EXERCISED> <message>`, which records one
#     JSON line per scenario id in $EVIDENCE_DIR/results.jsonl, prints
#     `RESULT <scenario-ids> <status>` as the last line, and exits 0 (PASS), 1 (FAIL),
#     3 (BLOCKED) or 4 (NOT_EXERCISED). A script that dies before it finishes is recorded
#     as FAIL by the EXIT trap.
#   - Negative-control scripts (kind negativeControl) report PASS when the control was
#     REJECTED as the contract requires ("the check exits non-zero"): their own exit
#     status is 0 then. A control that is not rejected is FAIL.
#   - Output rule: only counts, digests, exit codes, statuses and timestamps are ever
#     printed or recorded. No env value, DSN, token, mail host, name or address. Scripts
#     never `set -x`. Raw tool output goes to files in $EVIDENCE_DIR (redaction-grep.sh
#     scans them).
#   - Python is always `.venv/bin/python` (a plain `python3` may be a shim that refuses to run
#     on the machines this was written for); YAML is read with the PyYAML in that venv.

GOLIVE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GOLIVE_ROOT="$(cd "$GOLIVE_DIR/../../.." && pwd)"
GOLIVE_PHASE_DIR="$GOLIVE_ROOT/.kbd-orchestrator/phases/sellbird-go-live"
GOLIVE_FIXTURE="$GOLIVE_PHASE_DIR/fixtures/golive-required-tests.txt"
GOLIVE_PY="$GOLIVE_ROOT/.venv/bin/python"
GOLIVE_SCRIPT="$(basename "$0" .sh)"
GOLIVE_NS=sellbird
GOLIVE_KIND=scenario
GOLIVE_SCN=""
GOLIVE_STATUS=""
GOLIVE_RECORDED=""
GOLIVE_TREE_BEFORE=""
GOLIVE_SCRATCH=()
GOLIVE_DOCKER_IMAGES=()
GOLIVE_WORKTREES=()

# Reuse the stand-in helpers (sb_env_get, sb_gate_port, ...) and the kustomize image pin
# from the previous phase; nothing is duplicated.
# shellcheck source=scripts/local/lib.sh
source "$GOLIVE_ROOT/scripts/local/lib.sh"
# shellcheck source=scripts/boundary/preflight.sh
source "$GOLIVE_ROOT/scripts/boundary/preflight.sh"

# Environment variables that would steer a scratch or stand-in run toward a real database,
# a real gateway mode or a live cluster.
GOLIVE_CLEAN_ENV=(env -u SELLBIRD_HOME -u SELLBIRD_DASHBOARD_MODE -u SELLBIRD_DATABASE_URL
  -u SELLBIRD_MIGRATE_DATABASE_URL -u SELLBIRD_PUBLIC_HOST -u SELLBIRD_GATE_ISSUER
  -u SELLBIRD_GATE_AUDIENCE -u SELLBIRD_GATE_JWKS_URL -u SELLBIRD_GATE_ALLOWED_SUBS
  -u KUBERNETES_SERVICE_HOST)

export PYTHONDONTWRITEBYTECODE=1

# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

golive_have() { command -v "$1" > /dev/null 2>&1; }

golive_now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# golive_clean TEXT...: one line, no control characters, at most 400 characters.
golive_clean() { printf '%s' "$*" | tr '\r\n\t' '   ' | cut -c1-400; }

# golive_sha256 FILE
golive_sha256() {
  if golive_have sha256sum; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

# golive_iso_to_epoch ISO (YYYY-MM-DDTHH:MM:SSZ, no fraction): via jq, so no GNU/BSD date split.
golive_iso_to_epoch() { jq -rn --arg t "$1" '$t | fromdateiso8601'; }

# golive_epoch_to_iso EPOCH
golive_epoch_to_iso() { jq -rn --argjson e "$1" '$e | todate'; }

# golive_port_in_use PORT: true when something accepts a connection on, or listens on, the port.
golive_port_in_use() {
  local p="$1"
  if (exec 3<> "/dev/tcp/127.0.0.1/$p") 2> /dev/null; then
    return 0
  fi
  if golive_have lsof && lsof -nP -iTCP:"$p" -sTCP:LISTEN > /dev/null 2>&1; then
    return 0
  fi
  return 1
}

# golive_free_port START: print the first free port at or after START (scans 500 ports).
golive_free_port() {
  local p="$1" i=0
  while [ "$i" -lt 500 ]; do
    if ! golive_port_in_use "$p"; then
      printf '%s' "$p"
      return 0
    fi
    p=$((p + 1))
    i=$((i + 1))
  done
  return 1
}

# ---------------------------------------------------------------------------
# Evidence folder
# ---------------------------------------------------------------------------

# Resolution order: $EVIDENCE_DIR (an explicit folder is reused and only ever appended to);
# else the folder preflight.sh created (pointer file); else a NEW dated folder under
# evidence/boundary-run/. An existing default folder is never reused or overwritten.
# preflight.sh sets GOLIVE_NEW_EVIDENCE=1 so every boundary attempt gets its own folder.
golive_evidence_init() {
  if [ -n "${GOLIVE_EVIDENCE_READY:-}" ]; then
    return 0
  fi
  local base="$GOLIVE_PHASE_DIR/evidence/boundary-run"
  local ptr="$GOLIVE_PHASE_DIR/evidence/.boundary-run-current"
  local dir stamp n existing
  if [ -n "${EVIDENCE_DIR:-}" ]; then
    mkdir -p "$EVIDENCE_DIR"
    EVIDENCE_DIR="$(cd "$EVIDENCE_DIR" && pwd -P)"
  else
    existing=""
    if [ -z "${GOLIVE_NEW_EVIDENCE:-}" ] && [ -f "$ptr" ]; then
      existing="$(cat "$ptr")"
    fi
    if [ -n "$existing" ] && [ -d "$existing" ]; then
      EVIDENCE_DIR="$existing"
    else
      mkdir -p "$base"
      stamp="$(date -u +%Y%m%dT%H%M%SZ)"
      dir="$base/$stamp"
      n=1
      while ! mkdir "$dir" 2> /dev/null; do
        n=$((n + 1))
        if [ "$n" -gt 99 ]; then
          echo "cannot create a new evidence folder under $base" >&2
          exit 2
        fi
        dir="$base/$stamp-$n"
      done
      EVIDENCE_DIR="$dir"
      printf '%s\n' "$EVIDENCE_DIR" > "$ptr"
    fi
  fi
  export EVIDENCE_DIR
  GOLIVE_EVIDENCE_READY=1
}

# golive_artifact NAME: a path in the evidence folder that does not exist yet (NAME, NAME.2, ...).
golive_artifact() {
  golive_evidence_init
  local p="$EVIDENCE_DIR/$1" n=1
  while [ -e "$p" ]; do
    n=$((n + 1))
    p="$EVIDENCE_DIR/$1.$n"
  done
  printf '%s' "$p"
}

# ---------------------------------------------------------------------------
# Lifecycle: begin / record / finish
# ---------------------------------------------------------------------------

# golive_tree_state: a checksum of the tracked and untracked state of the working tree,
# outside .kbd-orchestrator (where the evidence folder lives). A control must not change it.
golive_tree_state() {
  git -C "$GOLIVE_ROOT" status --porcelain=v1 -- . ':(exclude).kbd-orchestrator' 2> /dev/null | LC_ALL=C sort | cksum
}

# golive_begin KIND SCENARIO_IDS: KIND is scenario, negativeControl or support.
golive_begin() {
  GOLIVE_KIND="$1"
  GOLIVE_SCN="$2"
  if ! golive_have jq; then
    echo "jq is required by the golive boundary scripts" >&2
    printf 'RESULT %s FAIL\n' "$GOLIVE_SCN"
    exit 2
  fi
  golive_evidence_init
  GOLIVE_LOG="$EVIDENCE_DIR/$GOLIVE_SCRIPT.log"
  exec > >(tee -a "$GOLIVE_LOG") 2>&1
  printf -- '--- %s %s kind=%s scenarios=%s ---\n' "$GOLIVE_SCRIPT" "$(golive_now_iso)" "$GOLIVE_KIND" "$GOLIVE_SCN"
  GOLIVE_TREE_BEFORE="$(golive_tree_state)"
  trap golive_on_exit EXIT
}

# record SCENARIO_ID STATUS MESSAGE...: append one JSON line to results.jsonl.
record() {
  local scn="$1" status="$2"
  shift 2
  local msg
  msg="$(golive_clean "$*")"
  case "$status" in
    PASS | FAIL | BLOCKED | NOT_EXERCISED) ;;
    *)
      msg="invalid status '$status': $msg"
      status=FAIL
      ;;
  esac
  golive_evidence_init
  jq -nc --arg ts "$(golive_now_iso)" --arg script "$GOLIVE_SCRIPT" --arg kind "$GOLIVE_KIND" \
    --arg scenario "$scn" --arg status "$status" --arg message "$msg" \
    '{ts: $ts, script: $script, kind: $kind, scenario: $scenario, status: $status, message: $message}' \
    >> "$EVIDENCE_DIR/results.jsonl"
  GOLIVE_RECORDED="$GOLIVE_RECORDED,$scn"
}

# record_detail: like record, but does not count as the scenario's final verdict.
record_detail() {
  local saved="$GOLIVE_RECORDED"
  record "$@"
  GOLIVE_RECORDED="$saved"
}

golive_cleanup() {
  local d wt
  for d in ${GOLIVE_DOCKER_IMAGES[@]+"${GOLIVE_DOCKER_IMAGES[@]}"}; do
    docker rmi -f "$d" > /dev/null 2>&1 || true
  done
  for wt in ${GOLIVE_WORKTREES[@]+"${GOLIVE_WORKTREES[@]}"}; do
    git -C "$GOLIVE_ROOT" worktree remove --force "$wt" > /dev/null 2>&1 || true
  done
  if [ "${#GOLIVE_WORKTREES[@]}" -gt 0 ]; then
    git -C "$GOLIVE_ROOT" worktree prune > /dev/null 2>&1 || true
  fi
  for d in ${GOLIVE_SCRATCH[@]+"${GOLIVE_SCRATCH[@]}"}; do
    if [ -n "$d" ] && [ -d "$d" ]; then
      rm -rf "$d"
    fi
  done
}

# golive_scratch: create a scratch directory (registered for cleanup) and print its path.
# Call as `golive_scratch_new; dir="$GOLIVE_LAST_SCRATCH"` (not in $(...), so the
# registration survives).
golive_scratch_new() {
  GOLIVE_LAST_SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/golive.XXXXXX")" || golive_finish BLOCKED "cannot create a scratch directory"
  GOLIVE_LAST_SCRATCH="$(cd "$GOLIVE_LAST_SCRATCH" && pwd -P)"
  GOLIVE_SCRATCH+=("$GOLIVE_LAST_SCRATCH")
}

golive_on_exit() {
  local rc=$?
  trap - EXIT
  golive_cleanup
  if [ -z "$GOLIVE_STATUS" ]; then
    local id
    for id in ${GOLIVE_SCN//,/ }; do
      case ",$GOLIVE_RECORDED," in
        *",$id,"*) ;;
        *) record "$id" FAIL "script aborted before it reached a verdict (exit $rc)" ;;
      esac
    done
    printf 'FAIL: script aborted before it reached a verdict (exit %s)\n' "$rc"
    printf 'RESULT %s FAIL\n' "$GOLIVE_SCN"
    if [ "$rc" -eq 0 ]; then
      rc=1
    fi
    exit "$rc"
  fi
}

# golive_finish STATUS MESSAGE...: record any scenario id not yet recorded with STATUS,
# print the verdict and the final RESULT line, and exit.
golive_finish() {
  local status="$1"
  shift
  local msg="$*" id after code
  if [ "$status" = PASS ] && [ -n "$GOLIVE_TREE_BEFORE" ]; then
    after="$(golive_tree_state)"
    if [ "$after" != "$GOLIVE_TREE_BEFORE" ]; then
      status=FAIL
      msg="the script changed the working tree (it must not): $msg"
    fi
  fi
  for id in ${GOLIVE_SCN//,/ }; do
    case ",$GOLIVE_RECORDED," in
      *",$id,"*) ;;
      *) record "$id" "$status" "$msg" ;;
    esac
  done
  GOLIVE_STATUS="$status"
  golive_cleanup
  printf '%s: %s\n' "$status" "$(golive_clean "$msg")"
  printf 'RESULT %s %s\n' "$GOLIVE_SCN" "$status"
  case "$status" in
    PASS) code=0 ;;
    FAIL) code=1 ;;
    BLOCKED) code=3 ;;
    *) code=4 ;;
  esac
  exit "$code"
}

# golive_note MESSAGE...: a progress line (counts and statuses only).
golive_note() { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$(golive_clean "$*")"; }

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

# golive_require_tools TOOL...: BLOCKED naming every missing tool.
golive_require_tools() {
  local t miss=""
  for t in "$@"; do
    if ! golive_have "$t"; then
      miss="$miss $t"
    fi
  done
  if [ -n "$miss" ]; then
    golive_finish BLOCKED "missing tools:$miss (run preflight.sh)"
  fi
}

# golive_require_venv: BLOCKED unless .venv/bin/python exists and imports the given modules.
golive_require_venv() {
  if [ ! -x "$GOLIVE_PY" ]; then
    golive_finish BLOCKED "no .venv/bin/python: create it (uv venv && uv pip install -e '.[dev,postgres,hosted]')"
  fi
  if [ "$#" -gt 0 ]; then
    local mod miss=""
    for mod in "$@"; do
      if ! "$GOLIVE_PY" -I -c "import $mod" > /dev/null 2>&1; then
        miss="$miss $mod"
      fi
    done
    if [ -n "$miss" ]; then
      golive_finish BLOCKED ".venv is missing python modules:$miss (uv pip install -e '.[dev,postgres,hosted]')"
    fi
  fi
}

# golive_base_sha: print the pre-phase commit the production edits are reverted to:
# $GOLIVE_BASE_REF if set, else the merge-base of HEAD and origin/main. Fails when it
# cannot be determined or equals HEAD (nothing to compare against).
golive_base_sha() {
  local base head
  if [ -n "${GOLIVE_BASE_REF:-}" ]; then
    base="$(git -C "$GOLIVE_ROOT" rev-parse --verify -q "${GOLIVE_BASE_REF}^{commit}")" || return 1
  else
    base="$(git -C "$GOLIVE_ROOT" merge-base HEAD origin/main 2> /dev/null)" || return 1
  fi
  head="$(git -C "$GOLIVE_ROOT" rev-parse HEAD)"
  if [ -z "$base" ] || [ "$base" = "$head" ]; then
    return 1
  fi
  printf '%s' "$base"
}

# golive_relevant_dirty: print the paths that matter to the boundary and are modified or
# untracked (anything the scratch worktrees and the CI runs would not see).
golive_relevant_dirty() {
  local paths=() p
  for p in tests sellbird infra .github scripts Dockerfile .dockerignore requirements.lock \
    pyproject.toml migrations prompts skills sellbird.yaml; do
    if [ -e "$GOLIVE_ROOT/$p" ]; then
      paths+=("$p")
    fi
  done
  git -C "$GOLIVE_ROOT" status --porcelain=v1 -- "${paths[@]}" | cut -c4-
}

# golive_load_ports: SELLBIRD_LOCAL_{PG,GATE,DIRECT}_PORT from the environment, else from
# ports.env in the evidence folder (written by preflight.sh), exported.
golive_load_ports() {
  local f k v
  golive_evidence_init
  f="$EVIDENCE_DIR/ports.env"
  if [ -f "$f" ]; then
    while IFS='=' read -r k v; do
      case "$k" in
        SELLBIRD_LOCAL_PG_PORT | SELLBIRD_LOCAL_GATE_PORT | SELLBIRD_LOCAL_DIRECT_PORT)
          if [ -z "${!k:-}" ] && [[ "$v" =~ ^[0-9]+$ ]]; then
            export "$k=$v"
          fi
          ;;
      esac
    done < "$f"
  fi
}

# golive_python3_shim_dir: print a directory holding a `python3` that runs .venv/bin/python
# (scripts/local/make-env.sh calls plain python3). A wrapper script, not a symlink, so the
# venv is found. Registered for cleanup.
golive_python3_shim_new() {
  golive_scratch_new
  GOLIVE_SHIM_DIR="$GOLIVE_LAST_SCRATCH"
  printf '#!/bin/sh\nexec "%s" "$@"\n' "$GOLIVE_PY" > "$GOLIVE_SHIM_DIR/python3"
  chmod 755 "$GOLIVE_SHIM_DIR/python3"
}

# golive_pg_dsns_export: export SELLBIRD_TEST_PG_MIGRATE_DSN / _APP_DSN for the local stand-in
# (never printed). Returns non-zero when the stand-in's .env is missing.
golive_pg_dsns_export() {
  if [ ! -f "$SB_ENV_FILE" ]; then
    return 1
  fi
  SELLBIRD_TEST_PG_MIGRATE_DSN="$(bash "$GOLIVE_ROOT/scripts/local/dsn.sh" migrate)" || return 1
  SELLBIRD_TEST_PG_APP_DSN="$(bash "$GOLIVE_ROOT/scripts/local/dsn.sh" app)" || return 1
  export SELLBIRD_TEST_PG_MIGRATE_DSN SELLBIRD_TEST_PG_APP_DSN
}

# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

# golive_kustomize DIR: render a kustomization to stdout with kustomize, else
# `kubectl kustomize`, else the pinned kustomize image (previous phase's pin).
golive_kustomize() {
  local dir
  dir="$(cd "$1" && pwd -P)"
  if golive_have kustomize; then
    kustomize build "$dir"
  elif golive_have kubectl && kubectl kustomize --help > /dev/null 2>&1; then
    kubectl kustomize "$dir"
  elif golive_have docker; then
    docker run --rm -v "$dir:/work:ro" -w /work "$SB_KUSTOMIZE_IMAGE" build .
  else
    return 127
  fi
}

# ---------------------------------------------------------------------------
# Live cluster (read-only except live-restart.sh's one pod delete)
# ---------------------------------------------------------------------------

# k ARGS...: kubectl against the approved context and the sellbird namespace only.
k() { kubectl --context "$GOLIVE_KUBE_CONTEXT" -n "$GOLIVE_NS" "$@"; }

# golive_kube_gate: BLOCKED unless GOLIVE_KUBE_CONTEXT names a context in the kubeconfig and
# the Deployment is readable. There is no default context: nothing guesses a cluster.
golive_kube_gate() {
  local ctxs nl
  if [ -z "${GOLIVE_KUBE_CONTEXT:-}" ]; then
    golive_finish BLOCKED "GOLIVE_KUBE_CONTEXT is not set; the live checks never guess a cluster"
  fi
  if ! golive_have kubectl; then
    golive_finish BLOCKED "kubectl is not installed"
  fi
  ctxs="$(kubectl config get-contexts -o name 2> /dev/null || true)"
  nl=$'\n'
  case "$nl$ctxs$nl" in
    *"$nl$GOLIVE_KUBE_CONTEXT$nl"*) ;;
    *) golive_finish BLOCKED "the context named by GOLIVE_KUBE_CONTEXT is not in the kubeconfig" ;;
  esac
  if ! k get deploy sellbird -o name > /dev/null 2>&1; then
    golive_finish BLOCKED "cannot read Deployment/sellbird in namespace sellbird with that context (cluster unreachable, no access, or not deployed)"
  fi
}

# golive_app_pod_json: the non-terminating app pods as a JSON array.
golive_app_pods_json() {
  k get pods -l app.kubernetes.io/name=sellbird,app.kubernetes.io/component=app -o json \
    | jq -c '[.items[] | select(.metadata.deletionTimestamp == null)]'
}

# golive_remote_snapshot CONTAINER [POD_START_ISO]: run _remote_snapshot.py inside the pod
# through the app's own storage layer. Prints one JSON line (counts, statuses, timestamps
# only; see the script) or nothing when the call failed. stderr is discarded on purpose:
# a traceback from the app could carry connection details.
golive_remote_snapshot() {
  local container="$1" start="${2:-}" code out
  code="$(cat "$GOLIVE_DIR/_remote_snapshot.py")"
  out="$(k exec deploy/sellbird -c "$container" -- python -c "$code" "$start" 2> /dev/null || true)"
  printf '%s\n' "$out" | grep '^{' | tail -n 1 || true
}
