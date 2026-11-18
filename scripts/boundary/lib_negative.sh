# Helpers for scripts/boundary/negative_controls.sh. Source it; do not execute it.
# shellcheck shell=bash

NC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NC_PROBES="$NC_ROOT/scripts/boundary/negative_probes.py"
NC_SCRATCH=()
NC_DOCKER_IMAGES=()
NC_TREE_BEFORE=""

# Environment variables that would steer a scratch run toward a real database or mode.
NC_CLEAN_ENV=(env -u SELLBIRD_HOME -u SELLBIRD_DASHBOARD_MODE -u SELLBIRD_DATABASE_URL
  -u SELLBIRD_MIGRATE_DATABASE_URL -u SELLBIRD_PUBLIC_HOST -u SELLBIRD_GATE_ISSUER
  -u SELLBIRD_GATE_AUDIENCE -u SELLBIRD_GATE_JWKS_URL -u SELLBIRD_GATE_ALLOWED_SUBS
  -u KUBERNETES_SERVICE_HOST)

export PYTHONDONTWRITEBYTECODE=1

nc_cleanup() {
  local image dir
  for image in ${NC_DOCKER_IMAGES[@]+"${NC_DOCKER_IMAGES[@]}"}; do
    docker rmi -f "$image" >/dev/null 2>&1 || true
  done
  for dir in ${NC_SCRATCH[@]+"${NC_SCRATCH[@]}"}; do
    [[ -n "$dir" && -d "$dir" ]] && rm -rf "$dir"
  done
}
trap nc_cleanup EXIT

# verdict PASS|FAIL|BLOCKED <reason>: print the final line and exit 0 / 1 / 2.
# After a PASS or FAIL the real working tree must be exactly as it was.
verdict() {
  local result="$1" reason="$2" after
  if [[ "$result" != BLOCKED && -n "$NC_TREE_BEFORE" ]]; then
    after="$(nc_tree_state)"
    if [[ "$after" != "$NC_TREE_BEFORE" ]]; then
      result=FAIL
      reason="the control changed the working tree (it must not): $reason"
    fi
  fi
  printf 'NEGATIVE-CONTROL %s %s: %s\n' "$NC_ID" "$result" "$reason"
  case "$result" in PASS) exit 0 ;; FAIL) exit 1 ;; *) exit 2 ;; esac
}

nc_tree_state() {
  git -C "$NC_ROOT" status --porcelain=v1 --ignored 2>/dev/null | sort | cksum
}

# nc_scratch: a new scratch directory in NC_DIR, registered for cleanup. Call it
# directly (not in $(...)), so the registration and any verdict take effect.
nc_scratch() {
  NC_DIR="$(mktemp -d "${TMPDIR:-/tmp}/negctl.XXXXXX")" || verdict BLOCKED "cannot create a scratch directory"
  NC_SCRATCH+=("$NC_DIR")
}

# Output shown on a FAIL: last lines, with connection strings masked.
nc_tail() {  # <text> [lines]
  printf '%s\n' "$1" | tail -n "${2:-12}" | sed -E 's#postgres(ql)?://[^[:space:]]+#postgresql://***#g; s/^/      | /'
}

nc_python() {
  if [[ -x "$NC_ROOT/.venv/bin/python" ]]; then printf '%s' "$NC_ROOT/.venv/bin/python"
  else command -v python3 || true
  fi
}

# nc_need_python: the interpreter that can import sellbird and pytest, else BLOCKED.
nc_need_python() {
  PY="$(nc_python)"
  [[ -n "$PY" ]] || verdict BLOCKED "no python interpreter (create .venv: pip install -e .)"
  PYTHONPATH="$NC_ROOT" "$PY" -c 'import sellbird, pytest, pytest_asyncio' >/dev/null 2>&1 \
    || verdict BLOCKED "$PY cannot import sellbird, pytest and pytest_asyncio (pip install -e .[dev])"
}

nc_need_docker() {
  command -v docker >/dev/null 2>&1 || verdict BLOCKED "docker is not installed"
  docker info >/dev/null 2>&1 || verdict BLOCKED "the docker daemon is not reachable"
}

# nc_load_pg: export the stand-in's DSNs for the test roles (never printed), else BLOCKED.
nc_load_pg() {
  local mig app
  mig="$("$NC_ROOT/scripts/local/dsn.sh" migrate 2>/dev/null)" \
    || verdict BLOCKED "no Postgres stand-in DSNs (run scripts/local/make-env.sh and bring the stand-in up)"
  app="$("$NC_ROOT/scripts/local/dsn.sh" app 2>/dev/null)" \
    || verdict BLOCKED "no Postgres stand-in DSNs (run scripts/local/make-env.sh and bring the stand-in up)"
  export SELLBIRD_TEST_PG_MIGRATE_DSN="$mig" SELLBIRD_TEST_PG_APP_DSN="$app"
}

# nc_probe <name>: run a probe from negative_probes.py in a scratch home and
# turn its last line into the verdict.
nc_probe() {
  local name="$1" home out rc line
  nc_scratch; home="$NC_DIR"
  out="$(cd "$home" && PYTHONPATH="$NC_ROOT" SELLBIRD_HOME="$home" "$PY" "$NC_PROBES" "$name" 2>&1)" && rc=0 || rc=$?
  line="$(printf '%s\n' "$out" | tail -n 1)"
  case "$rc:$line" in
    0:"PROBE PASS: "*) verdict PASS "${line#PROBE PASS: }" ;;
    1:"PROBE FAIL: "*) verdict FAIL "${line#PROBE FAIL: }" ;;
    2:"PROBE BLOCKED: "*) verdict BLOCKED "${line#PROBE BLOCKED: }" ;;
    *) nc_tail "$out" 15 >&2; verdict FAIL "probe $name ended unexpectedly (exit $rc)" ;;
  esac
}

# nc_scratch_tree [plant]: a copy of the working tree in a scratch directory
# (NC_DIR), optionally with a planted defect (dedup|log).
nc_scratch_tree() {
  local tree
  nc_scratch; tree="$NC_DIR"
  "$(nc_python)" "$NC_PROBES" copy-tree "$NC_ROOT" "$tree" >/dev/null 2>&1 \
    || verdict BLOCKED "cannot copy the working tree (is this a git checkout?)"
  if [[ -n "${1:-}" ]]; then
    local out rc
    out="$("$(nc_python)" "$NC_PROBES" plant "$1" "$tree" 2>&1)" && rc=0 || rc=$?
    [[ "$rc" -eq 0 ]] || verdict BLOCKED "${out#PROBE BLOCKED: }"
  fi
  NC_DIR="$tree"
}
