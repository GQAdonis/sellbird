#!/usr/bin/env bash
# SCN-LOCK-001 negative control (b): a scratch copy of pyproject.toml with ONE dependency bound
# changed, the lock left as is, must make scripts/ci/check-lock-fresh.sh exit non-zero WITH its
# "is stale" message (a resolver error would also be non-zero but is the wrong reason).
# Packet:  neg-lock-stale.sh SCN-LOCK-001
# The scratch tree holds copies of scripts/ci, Dockerfile, README.md, requirements.lock and the
# mutated pyproject.toml, so the real scripts run against it (they locate their root from their
# own path). First the UNMUTATED scratch copy must pass (so the mutation is the only difference).
# The mutation caps a dependency below its currently locked version (`name<VERSION`), which forces a
# different resolution; candidates are tried in order until one resolves. Needs uv at the pinned
# version and network.
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin negativeControl SCN-LOCK-001
cd "$GOLIVE_ROOT"

golive_require_tools uv
golive_require_venv
if [ ! -f requirements.lock ]; then
  golive_finish BLOCKED "requirements.lock does not exist: a human must run scripts/ci/lock-requirements.sh and commit it"
fi
golive_scratch_new
tmp="$GOLIVE_LAST_SCRATCH"
mkdir -p "$tmp/base/scripts"
cp -R scripts/ci "$tmp/base/scripts/ci"
cp Dockerfile pyproject.toml README.md requirements.lock "$tmp/base/"
raw="$(golive_artifact raw-neg-lock-stale.log)"
rc=0
bash "$tmp/base/scripts/ci/check-lock-fresh.sh" >> "$raw" 2>&1 || rc=$?
if [ "$rc" -ne 0 ]; then
  golive_finish FAIL "the unmutated scratch copy already fails the stale-lock check (exit $rc; see $(basename "$raw")): wrong uv, no network, or a genuinely stale lock"
fi
golive_note "unmutated scratch copy passes the stale-lock check"

for pkg in pytz python-dotenv httpx beautifulsoup4 dnspython; do
  pin="$(sed -n "s/^${pkg}==\\([^ ;\\\\]*\\).*/\\1/p" requirements.lock | head -n 1)"
  if [ -z "$pin" ]; then
    continue
  fi
  w="$tmp/mut-$pkg"
  mkdir -p "$w/scripts"
  cp -R "$tmp/base/scripts/ci" "$w/scripts/ci"
  cp "$tmp/base/Dockerfile" "$tmp/base/README.md" "$tmp/base/requirements.lock" "$w/"
  if ! "$GOLIVE_PY" -I - "$tmp/base/pyproject.toml" "$w/pyproject.toml" "$pkg" "$pin" <<'PY'
import re, sys
src, dst, pkg, pin = sys.argv[1:5]
t = open(src).read()
new, n = re.subn(r'"%s[^"]*"' % re.escape(pkg), '"%s<%s"' % (pkg, pin), t, count=1)
if n != 1:
    raise SystemExit(1)
open(dst, "w").write(new)
PY
  then
    continue
  fi
  out="$(golive_artifact "neg-lock-stale-$pkg.out")"
  rc=0
  bash "$w/scripts/ci/check-lock-fresh.sh" > "$out" 2>&1 || rc=$?
  cat "$out" >> "$raw"
  if [ "$rc" -ne 0 ] && grep -q 'is stale' "$out"; then
    golive_finish PASS "with the bound of one dependency changed the stale-lock check exited $rc and said the lock is stale"
  fi
  golive_note "candidate $pkg: exit $rc without the stale message; trying the next dependency"
done
golive_finish FAIL "no candidate mutation made the stale-lock check report a stale lock (see $(basename "$raw"))"
