#!/usr/bin/env bash
# Fail when requirements.lock no longer matches pyproject.toml: regenerate it
# into a temporary copy (existing pins kept as preferences, so new upstream
# releases alone do not make it stale) and compare.
#
#   scripts/ci/check-lock-fresh.sh
#
# Exit 0 when fresh; 1 when missing, unhashed or stale (the difference is
# printed: package names, versions and hashes only). Needs uv at the version in
# scripts/ci/uv-version and network access to PyPI. (OpenSpec change
# pipeline-hardening, 1.5.)
set -euo pipefail
# shellcheck source=scripts/ci/lock-lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lock-lib.sh"

[[ -f "$LOCK_FILE" ]] || lock_die "requirements.lock is missing: run $LOCK_COMMAND and commit it"
grep -q -- '--hash=sha256:' "$LOCK_FILE" || lock_die "requirements.lock has no hashes: run $LOCK_COMMAND"
lock_preflight

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cp "$LOCK_FILE" "$work/requirements.lock"
lock_compile "$work/requirements.lock"

if ! diff -u "$LOCK_FILE" "$work/requirements.lock"; then
  lock_die "requirements.lock is stale: run $LOCK_COMMAND and commit the result"
fi
echo "requirements.lock matches pyproject.toml."
