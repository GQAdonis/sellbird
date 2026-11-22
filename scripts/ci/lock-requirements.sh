#!/usr/bin/env bash
# Regenerate requirements.lock (hash-locked image dependencies) from
# pyproject.toml. Run it after changing [project.dependencies] or the `hosted`
# or `postgres` extras, and commit the result. Existing pins are kept unless
# pyproject.toml needs a change; to move every pin to the newest allowed
# version, delete requirements.lock first.
#
#   scripts/ci/lock-requirements.sh
#
# Needs uv at the version in scripts/ci/uv-version and network access to PyPI.
# (OpenSpec change pipeline-hardening, 1.5.)
set -euo pipefail
# shellcheck source=scripts/ci/lock-lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lock-lib.sh"

lock_preflight
lock_compile "$LOCK_FILE"
grep -q -- '--hash=sha256:' "$LOCK_FILE" || lock_die "uv wrote no hashes to $LOCK_FILE"
echo "Wrote requirements.lock ($(grep -c -- '--hash=sha256:' "$LOCK_FILE") hashes)."
