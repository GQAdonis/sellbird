#!/usr/bin/env bash
# SCN-FRESH-001 negative control: two mutated copies of the base must each be rejected by the same
# check, naming the offender. Copy 1: the migration ServiceAccount's Argo CD annotations removed.
# Copy 2: the NodeLocal DNS peer widened to 169.254.0.0/16. The unmutated base must pass first, so
# the difference is the mutation. Packet:  neg-fresh.sh SCN-FRESH-001
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin negativeControl SCN-FRESH-001
cd "$GOLIVE_ROOT"

golive_require_venv yaml
base="infra/k8s/base"
golive_scratch_new
tmp="$GOLIVE_LAST_SCRATCH"
chk() { "$GOLIVE_PY" -I "$GOLIVE_DIR/_fresh.py" check "$1"; }

golive_kustomize "$base" > "$tmp/base.yaml" || golive_finish BLOCKED "could not render $base"
chk "$tmp/base.yaml" > /dev/null || golive_finish FAIL "the unmutated base is already rejected; the control proves nothing"

bad=0
"$GOLIVE_PY" -I "$GOLIVE_DIR/_fresh.py" mutate-hook "$base" "$tmp/no-hook"
golive_kustomize "$tmp/no-hook" > "$tmp/no-hook.yaml" || golive_finish BLOCKED "could not render the mutated copy"
rc=0
out="$(chk "$tmp/no-hook.yaml" 2>&1)" || rc=$?
printf '%s\n' "$out" | grep '^FAIL' || true
if [ "$rc" -ne 0 ] && grep -q 'ServiceAccount/sellbird-migrate' <<< "$out"; then
  golive_note "copy 1 rejected, naming ServiceAccount/sellbird-migrate"
else
  golive_note "copy 1 NOT rejected as required (exit $rc)"
  bad=$((bad + 1))
fi

"$GOLIVE_PY" -I "$GOLIVE_DIR/_fresh.py" mutate-dns "$base" "$tmp/wide-dns"
golive_kustomize "$tmp/wide-dns" > "$tmp/wide-dns.yaml" || golive_finish BLOCKED "could not render the mutated copy"
rc=0
out="$(chk "$tmp/wide-dns.yaml" 2>&1)" || rc=$?
printf '%s\n' "$out" | grep '^FAIL' || true
if [ "$rc" -ne 0 ] && grep -q '169\.254\.0\.0/16' <<< "$out"; then
  golive_note "copy 2 rejected, naming peer 169.254.0.0/16"
else
  golive_note "copy 2 NOT rejected as required (exit $rc)"
  bad=$((bad + 1))
fi

if [ "$bad" -gt 0 ]; then
  golive_finish FAIL "$bad of 2 mutated copies were not rejected"
fi
golive_finish PASS "both mutated copies rejected: missing hook names ServiceAccount/sellbird-migrate, widened DNS names 169.254.0.0/16"
