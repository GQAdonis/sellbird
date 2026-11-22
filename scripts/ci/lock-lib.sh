# Shared by lock-requirements.sh and check-lock-fresh.sh. Source it.
# shellcheck shell=bash
#
# requirements.lock is the image's only dependency input: pyproject.toml's
# runtime dependencies plus the `hosted` and `postgres` extras, every version
# pinned and every distribution hashed, resolved once for all platforms
# (--universal) so the same file serves linux/amd64 and linux/arm64. The image's
# Python minor version (python:3.12 in the Dockerfile) is the resolution floor.
# requirements.txt stays the unlocked developer file.

LOCK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCK_FILE="$LOCK_ROOT/requirements.lock"
LOCK_PYTHON_VERSION=3.12
LOCK_UV_VERSION="$(tr -d '[:space:]' < "$LOCK_ROOT/scripts/ci/uv-version")"
LOCK_COMMAND="scripts/ci/lock-requirements.sh"

lock_die() {
  printf '%s: %s\n' "$(basename "$0")" "$*" >&2
  exit 1
}

# lock_preflight: uv is the pinned version and the Dockerfile still builds on
# the Python minor version the lock is resolved for.
lock_preflight() {
  command -v uv > /dev/null 2>&1 || lock_die "uv is required (version $LOCK_UV_VERSION)"
  local have
  have="$(uv --version | awk '{print $2}')"
  [[ "$have" == "$LOCK_UV_VERSION" ]] \
    || lock_die "uv $have found; the lock is generated with uv $LOCK_UV_VERSION (scripts/ci/uv-version)"
  grep -Eq "^ARG PYTHON_IMAGE=python:${LOCK_PYTHON_VERSION//./\\.}\." "$LOCK_ROOT/Dockerfile" \
    || lock_die "the Dockerfile's PYTHON_IMAGE is not python:$LOCK_PYTHON_VERSION; update LOCK_PYTHON_VERSION"
}

# lock_compile OUTPUT: resolve into OUTPUT. When OUTPUT already exists its pins
# are kept as preferences, so an unchanged pyproject.toml gives the same file
# even after new upstream releases.
lock_compile() {
  (
    cd "$LOCK_ROOT"
    uv pip compile pyproject.toml \
      --no-config \
      --default-index https://pypi.org/simple \
      --extra hosted \
      --extra postgres \
      --universal \
      --python-version "$LOCK_PYTHON_VERSION" \
      --generate-hashes \
      --custom-compile-command "$LOCK_COMMAND" \
      --quiet \
      --output-file "$1"
  )
}
