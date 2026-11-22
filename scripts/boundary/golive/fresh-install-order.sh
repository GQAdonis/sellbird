#!/usr/bin/env bash
# SCN-FRESH-001 (static): render a kustomize base and check
#   (a) the migration Job's ServiceAccount is itself a PreSync hook with a lower sync-wave than the
#       Job (it must exist before the Job on a fresh install; "absent from the render" is a FAIL),
#   (b) the port 53 egress peers across all NetworkPolicies are exactly the kube-dns pods and
#       169.254.20.10/32, and no other link-local address is allowed.
# Packet:  bash scripts/boundary/golive/fresh-install-order.sh infra/k8s/base SCN-FRESH-001
# Static only: a real install into an empty namespace is not run (contract limitation).
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin scenario SCN-FRESH-001
cd "$GOLIVE_ROOT"

base="${1:-infra/k8s/base}"
golive_require_venv yaml
if [ ! -f "$base/kustomization.yaml" ]; then
  golive_finish BLOCKED "no kustomization.yaml in $base"
fi
rendered="$(golive_artifact fresh-rendered.yaml)"
rc=0
golive_kustomize "$base" > "$rendered" 2> "$rendered.err" || rc=$?
if [ "$rc" -ne 0 ] || [ ! -s "$rendered" ]; then
  golive_finish BLOCKED "could not render $base (exit $rc; see $(basename "$rendered").err)"
fi
rc=0
"$GOLIVE_PY" -I "$GOLIVE_DIR/_fresh.py" check "$rendered" || rc=$?
if [ "$rc" -ne 0 ]; then
  golive_finish FAIL "the rendered base breaks the fresh-install ordering or the DNS egress rule"
fi
golive_finish PASS "migration ServiceAccount is an earlier PreSync hook; port 53 peers are exactly kube-dns and 169.254.20.10/32"
