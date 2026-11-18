# Shared helpers for scripts/local/*.sh. Source it; do not execute it.
# shellcheck shell=bash

SB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SB_LOCAL="$SB_ROOT/infra/local"
SB_ENV_FILE="$SB_LOCAL/.env"
SB_GEN="$SB_LOCAL/.env.generated"
SB_COMPOSE=(docker compose -f "$SB_LOCAL/compose.yaml")

sb_die() {
  printf '%s: %s\n' "$(basename "$0")" "$*" >&2
  exit 1
}

# sb_env_get KEY: print KEY's value from infra/local/.env (surrounding single
# quotes removed). Fails when the file or the key is missing. Never echo the
# result to a terminal for secret keys; capture it.
sb_env_get() {
  [[ -f "$SB_ENV_FILE" ]] || sb_die "$SB_ENV_FILE not found: run scripts/local/make-env.sh"
  local line
  line="$(grep -E "^$1=" "$SB_ENV_FILE" | tail -n 1)" || sb_die "$1 is not in $SB_ENV_FILE"
  line="${line#*=}"
  line="${line#\'}"
  line="${line%\'}"
  [[ -n "$line" ]] || sb_die "$1 is empty in $SB_ENV_FILE"
  printf '%s' "$line"
}

# sb_python: Sellbird's .venv interpreter when present (it has PyYAML), else python3.
sb_python() {
  if [[ -x "$SB_ROOT/.venv/bin/python" ]]; then
    printf '%s' "$SB_ROOT/.venv/bin/python"
  else
    command -v python3 || sb_die "python3 is required"
  fi
}
