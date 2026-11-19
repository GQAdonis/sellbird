#!/usr/bin/env bash
# Boundary check for Sellbird's Kubernetes manifests and the deploy bot's pin guard
# (OpenSpec change gitops-deploy-sellbird, spec image-delivery).
#
# Usage: scripts/boundary/check_manifests.sh <overlay-dir>
#   e.g. scripts/boundary/check_manifests.sh infra/k8s/overlays/example
#
# Part 1 renders the overlay with the digest-pinned kustomize from
# scripts/boundary/preflight.sh (Docker only; nothing installed on the host) and
# asserts on the rendered objects:
#   - every workload image is <registry>/<owner>/sellbird:<40 hex>@sha256:<64 hex>;
#   - a default-deny NetworkPolicy (podSelector {}, Ingress and Egress, no rules)
#     and ingress only from flint-gate pods in namespace flint-gate;
#   - every container: readOnlyRootFilesystem true, runAsNonRoot, not uid 0,
#     allowPrivilegeEscalation false, capabilities drop ALL and add nothing, not
#     privileged; pods: seccomp RuntimeDefault, no host namespaces;
#   - a migration Job with the Argo CD PreSync hook, using only Secret
#     sellbird-db-migrate; the app never receives sellbird-db-migrate;
#   - secrets only through env secretKeyRef: no Secret objects, no envFrom
#     secretRef, no Secret or projected volumes, no literal value on a
#     secret-looking env name or ConfigMap key;
#   - no Namespace object, only the AppProject's kinds, all in namespace sellbird,
#     ServiceAccount without a token, Service of type ClusterIP;
#   - no real hostname or email literal in the render or in infra/k8s sources:
#     a hostname must end in example.test (or another reserved example domain),
#     svc.cluster.local, a known registry or a Kubernetes/Argo CD API domain.
# Part 2 exercises scripts/deploy/pin_overlay.sh against scratch git repositories
# it creates under a temporary directory: a valid forward pin is accepted and
# changes exactly the newTag and digest lines; a tag-only image, a backwards or
# diverged pin, a malformed digest or tag, a wrong image name, a broken entry
# order and a dirty checkout are refused, and the repository is unchanged after
# each refusal.
#
# Prints one FAIL line per failed assertion and exits 1 if any failed, 0 if all
# passed, 2 on a usage or tooling error.

set -u -o pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <overlay-dir relative to the repository root>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OVERLAY="${1%/}"
case "$OVERLAY" in
  "$ROOT"/*) OVERLAY="${OVERLAY#"$ROOT"/}" ;;
  /*|*..*) echo "error: overlay must be a path inside the repository" >&2; exit 2 ;;
esac
[ -f "$ROOT/$OVERLAY/kustomization.yaml" ] || { echo "error: no kustomization.yaml in $OVERLAY" >&2; exit 2; }

# shellcheck source=preflight.sh
SB_ROOT="$ROOT"  # a prefix assignment on `.` would be reverted afterwards
. "$ROOT/scripts/boundary/preflight.sh"
set +e  # preflight sets -e when sourced; this script counts failures instead

WORK="$(mktemp -d "${TMPDIR:-/tmp}/check_manifests.XXXXXX")" || exit 2
trap 'rm -rf "$WORK"' EXIT

failures=0
checks=0
fail() { echo "FAIL: $*"; failures=$((failures + 1)); }
ok() { checks=$((checks + 1)); }
# expect_empty <label> <output>: the output must be empty (it lists offenders).
expect_empty() {
  ok
  if [ -n "$2" ]; then
    fail "$1: $(printf '%s' "$2" | tr '\n' ' ')"
  fi
}

# ---------------------------------------------------------------- part 1: render
RENDERED="$WORK/rendered.yaml"
DOCS="$WORK/docs.json"
if ! sb_kustomize build "$OVERLAY" > "$RENDERED" 2> "$WORK/kustomize.err"; then
  echo "error: kustomize build $OVERLAY failed:" >&2
  cat "$WORK/kustomize.err" >&2
  exit 2
fi
if ! sb_yq_stdin ea -o=json '[.]' < "$RENDERED" > "$DOCS" 2> "$WORK/yq.err"; then
  echo "error: could not parse the rendered manifests:" >&2
  cat "$WORK/yq.err" >&2
  exit 2
fi

# q <expr>: run a yq expression over the JSON array of rendered objects.
q() {
  sb_yq_stdin --input-format=json --output-format=yaml "$1" < "$DOCS" 2>> "$WORK/yq.err"
}

WORKLOADS='.[] | select(.kind == "Deployment" or .kind == "Job")'
# Each container of each workload, with $w (workload) and $p (pod spec) bound.
CONTAINERS="$WORKLOADS | . as \$w | .spec.template.spec as \$p | ((\$p.containers // []) + (\$p.initContainers // [])) | .[]"
WHO='$w.kind + "/" + $w.metadata.name + "/" + .name'

echo "check_manifests: rendered $OVERLAY ($(q '. | length') objects)"

# Kinds, namespace, no Namespace object.
expect_empty "Namespace object rendered (namespaces are platform-owned)" \
  "$(q '.[] | select(.kind == "Namespace") | .metadata.name')"
expect_empty "kind outside the AppProject whitelist" \
  "$(q '.[] | select(.kind != "Deployment" and .kind != "Service" and .kind != "ServiceAccount" and .kind != "ConfigMap" and .kind != "NetworkPolicy" and .kind != "Job") | .kind + "/" + .metadata.name')"
expect_empty "object not in namespace sellbird" \
  "$(q '.[] | select(.metadata.namespace != "sellbird") | .kind + "/" + .metadata.name')"
ok; [ "$(q '[.[] | select(.kind == "Deployment")] | length')" = "1" ] || fail "expected exactly one Deployment"
expect_empty "ServiceAccount mounts a token" \
  "$(q '.[] | select(.kind == "ServiceAccount" and .automountServiceAccountToken != false) | .metadata.name')"
expect_empty "Service is not ClusterIP" \
  "$(q '.[] | select(.kind == "Service" and (.spec.type // "ClusterIP") != "ClusterIP") | .metadata.name')"

# Image pinning: tag and digest on every workload container.
images="$(q "$CONTAINERS | .image")"
ok; [ -n "$images" ] || fail "no workload images rendered"
while IFS= read -r image; do
  [ -n "$image" ] || continue
  ok
  [[ "$image" =~ ^[a-z0-9.-]+(:[0-9]+)?/[a-z0-9._/-]+/sellbird:[0-9a-f]{40}@sha256:[0-9a-f]{64}$ ]] \
    || fail "image is not pinned as <name>:<40-hex sha>@sha256:<digest>: $image"
done <<< "$images"
ok; [ "$(printf '%s\n' "$images" | sort -u | grep -c .)" = "1" ] \
  || fail "app and migration Job do not use the same pinned image"

# NetworkPolicy.
ok; [ "$(q '[.[] | select(.kind == "NetworkPolicy" and ((.spec.podSelector // {}) | length) == 0 and .spec.ingress == null and .spec.egress == null and ((.spec.policyTypes // []) | contains(["Ingress", "Egress"])))] | length')" -ge 1 ] 2>/dev/null \
  || fail "no default-deny NetworkPolicy (podSelector {}, policyTypes Ingress and Egress, no rules)"
peers="$(q '.[] | select(.kind == "NetworkPolicy") | (.spec.ingress // []) | .[] | (.from // []) | .[] | (.namespaceSelector.matchLabels["kubernetes.io/metadata.name"] // "-") + "|" + (.podSelector.matchLabels["app.kubernetes.io/name"] // "-") + "|" + (.ipBlock.cidr // "-")')"
ok; [ -n "$peers" ] || fail "no ingress allowance from flint-gate"
expect_empty "ingress peer other than flint-gate pods in namespace flint-gate" \
  "$(printf '%s\n' "$peers" | grep . | grep -vxF 'flint-gate|flint-gate|-')"
expect_empty "ingress rule without a 'from' (allows every source)" \
  "$(q '.[] | select(.kind == "NetworkPolicy") | select(((.spec.ingress // []) | map(select(((.from // []) | length) == 0)) | length) > 0) | .metadata.name')"
expect_empty "ingress port other than 5555" \
  "$(q '.[] | select(.kind == "NetworkPolicy") | (.spec.ingress // []) | .[] | (.ports // [{"port": "any"}]) | .[] | select(.port != 5555) | .port')"

# Pod and container security.
expect_empty "readOnlyRootFilesystem is not true" \
  "$(q "$CONTAINERS | select(.securityContext.readOnlyRootFilesystem != true) | $WHO")"
expect_empty "runAsNonRoot is not true" \
  "$(q "$CONTAINERS | select(.securityContext.runAsNonRoot == false or (.securityContext.runAsNonRoot == null and \$p.securityContext.runAsNonRoot != true)) | $WHO")"
expect_empty "runs as uid 0" \
  "$(q "$CONTAINERS | select(.securityContext.runAsUser == 0 or (.securityContext.runAsUser == null and \$p.securityContext.runAsUser == 0)) | $WHO")"
expect_empty "allowPrivilegeEscalation is not false" \
  "$(q "$CONTAINERS | select(.securityContext.allowPrivilegeEscalation != false) | $WHO")"
expect_empty "capabilities do not drop ALL" \
  "$(q "$CONTAINERS | select(((.securityContext.capabilities.drop // []) | contains([\"ALL\"])) | not) | $WHO")"
expect_empty "capabilities added" \
  "$(q "$CONTAINERS | select(((.securityContext.capabilities.add // []) | length) > 0) | $WHO")"
expect_empty "privileged container" \
  "$(q "$CONTAINERS | select(.securityContext.privileged == true) | $WHO")"
expect_empty "pod seccompProfile is not RuntimeDefault" \
  "$(q "$WORKLOADS | select(.spec.template.spec.securityContext.seccompProfile.type != \"RuntimeDefault\") | .kind + \"/\" + .metadata.name")"
expect_empty "pod uses a host namespace" \
  "$(q "$WORKLOADS | select(.spec.template.spec.hostNetwork == true or .spec.template.spec.hostPID == true or .spec.template.spec.hostIPC == true) | .kind + \"/\" + .metadata.name")"
expect_empty "pod mounts a service account token" \
  "$(q "$WORKLOADS | select(.spec.template.spec.automountServiceAccountToken != false) | .kind + \"/\" + .metadata.name")"

# Migration Job.
ok; [ "$(q '[.[] | select(.kind == "Job" and .metadata.annotations["argocd.argoproj.io/hook"] == "PreSync")] | length')" = "1" ] \
  || fail "expected exactly one migration Job annotated argocd.argoproj.io/hook: PreSync"
ok; [ "$(q '.[] | select(.kind == "Job") | .spec.template.spec.containers[0].args | join(" ")')" = "storage migrate" ] \
  || fail "migration Job does not run 'storage migrate'"
JOB_SECRETS="$(q '.[] | select(.kind == "Job") | .spec.template.spec.containers[] | (.env // []) | .[] | select(.valueFrom.secretKeyRef != null) | .valueFrom.secretKeyRef.name' | sort -u)"
ok; [ "$JOB_SECRETS" = "sellbird-db-migrate" ] \
  || fail "migration Job must use only Secret sellbird-db-migrate (has: $(printf '%s' "$JOB_SECRETS" | tr '\n' ' '))"
APP_SECRETS="$(q '.[] | select(.kind == "Deployment") | .spec.template.spec.containers[] | (.env // []) | .[] | select(.valueFrom.secretKeyRef != null) | .valueFrom.secretKeyRef.name' | sort -u)"
ok; printf '%s\n' "$APP_SECRETS" | grep -qxF sellbird-db-migrate && fail "app receives the migration Secret sellbird-db-migrate"
ok; { printf '%s\n' "$APP_SECRETS" | grep -qxF sellbird-db-app && printf '%s\n' "$APP_SECRETS" | grep -qxF sellbird-claude; } \
  || fail "app does not reference sellbird-db-app and sellbird-claude by secretKeyRef"

# Secret references by name and key only.
SECRET_NAME_RE='(?i)(DATABASE_URL|TOKEN|PASSWORD|PASSWD|SECRET|PRIVATE|CREDENTIAL|API_KEY|_KEY$)'
expect_empty "Secret object rendered (Secrets are operator-created)" \
  "$(q '.[] | select(.kind == "Secret") | .metadata.name')"
expect_empty "envFrom secretRef (inject single keys with secretKeyRef)" \
  "$(q "$CONTAINERS | (.envFrom // []) | .[] | select(.secretRef != null) | .secretRef.name")"
expect_empty "Secret or projected volume" \
  "$(q "$WORKLOADS | (.spec.template.spec.volumes // []) | .[] | select(.secret != null or .projected != null) | .name")"
expect_empty "literal value on a secret-looking env name" \
  "$(q "$CONTAINERS | (.env // []) | .[] | select(.value != null and (.name | test(\"$SECRET_NAME_RE\"))) | .name")"
expect_empty "secret-looking env name not from secretKeyRef" \
  "$(q "$CONTAINERS | (.env // []) | .[] | select((.name | test(\"$SECRET_NAME_RE\")) and .valueFrom.secretKeyRef == null) | .name")"
expect_empty "secret-looking ConfigMap key" \
  "$(q ".[] | select(.kind == \"ConfigMap\") | (.data // {}) | keys | .[] | select(test(\"$SECRET_NAME_RE\"))")"

# Hostnames and emails: the render plus every source file under infra/k8s.
ALLOWED_HOST_RE='(^|\.)(example\.(test|com|net|org)|svc\.cluster\.local|ghcr\.io|registry\.k8s\.io|docker\.io|kubernetes\.io|k8s\.io|argoproj\.io)$'
FILE_EXT_RE='\.(md|ya?ml|json|sh|py|txt|env)$'
host_scan() {  # host_scan <file>: print hostname-like tokens that are not allowed
  # A token preceded by a single "/" is a path segment or label-key suffix
  # (kubernetes.io/metadata.name), not a host; after "//" it is a URL host.
  LC_ALL=C grep -oiE '(^|[^/A-Za-z0-9.-]|//)([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}' "$1" \
    | tr 'A-Z' 'a-z' | sed -E 's/^.*[^a-z0-9.-]//' \
    | grep -vE "$ALLOWED_HOST_RE" | grep -vE "$FILE_EXT_RE" | sort -u
}
email_scan() {
  LC_ALL=C grep -oiE '[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}' "$1" | tr 'A-Z' 'a-z' \
    | grep -vE '@example\.(test|com|net|org)$' | sort -u
}
SCAN_FILES="$RENDERED"
while IFS= read -r f; do SCAN_FILES="$SCAN_FILES
$f"; done < <(find "$ROOT/infra/k8s" -type f | sort)
while IFS= read -r f; do
  [ -n "$f" ] || continue
  label="${f#"$ROOT"/}"; [ "$f" = "$RENDERED" ] && label="rendered $OVERLAY"
  expect_empty "hostname literal that is not a placeholder in $label" "$(host_scan "$f")"
  expect_empty "email address that is not a placeholder in $label" "$(email_scan "$f")"
done <<< "$SCAN_FILES"

if [ -s "$WORK/yq.err" ]; then
  fail "yq reported errors: $(head -c 400 "$WORK/yq.err" | tr '\n' ' ')"
fi

# ------------------------------------------------------- part 2: pin_overlay.sh
PIN="$ROOT/scripts/deploy/pin_overlay.sh"
OVL_FILE="apps/sellbird/overlays/production/kustomization.yaml"
IMAGE="ghcr.io/example-owner/sellbird"

# Isolate from the operator's git config (signing, hooks, templates).
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME="Example Bot" GIT_AUTHOR_EMAIL="bot@example.com"
export GIT_COMMITTER_NAME="Example Bot" GIT_COMMITTER_EMAIL="bot@example.com"

hex64() { printf '%064d' 0 | tr 0 "$1"; }   # hex64 a -> aaaa... (64)
D2="sha256:$(hex64 2)"
D3="sha256:$(hex64 3)"

SRC="$WORK/source"
git init -q -b main "$SRC" || exit 2
git -C "$SRC" commit -q --allow-empty -m c1 && C1="$(git -C "$SRC" rev-parse HEAD)"
git -C "$SRC" commit -q --allow-empty -m c2 && C2="$(git -C "$SRC" rev-parse HEAD)"
git -C "$SRC" commit -q --allow-empty -m c3 && C3="$(git -C "$SRC" rev-parse HEAD)"
git -C "$SRC" checkout -q -b side "$C1" && git -C "$SRC" commit -q --allow-empty -m cx \
  && CX="$(git -C "$SRC" rev-parse HEAD)" && git -C "$SRC" checkout -q main

# make_overlay <dir> <entry-lines...>: a platform repository with one commit.
make_overlay() {
  local dir=$1; shift
  git init -q -b main "$dir" || return 1
  mkdir -p "$dir/$(dirname "$OVL_FILE")"
  {
    echo "apiVersion: kustomize.config.k8s.io/v1beta1"
    echo "kind: Kustomization"
    echo "resources:"
    echo "  - https://example.test/example-owner/sellbird//infra/k8s/base?ref=$C1"
    echo "images:"
    printf '%s\n' "$@"
  } > "$dir/$OVL_FILE"
  git -C "$dir" add -A && git -C "$dir" commit -q -m init
}
GOOD_ENTRY=("  - name: sellbird" "    newName: $IMAGE" "    newTag: \"$C2\"" "    digest: $D2")

OVL="$WORK/overlay"
make_overlay "$OVL" "${GOOD_ENTRY[@]}" || exit 2
BASE_HEAD="$(git -C "$OVL" rev-parse HEAD)"

snapshot() {  # snapshot <repo>: HEAD, status and file checksum
  printf '%s|%s|%s' "$(git -C "$1" rev-parse HEAD)" \
    "$(git -C "$1" status --porcelain --untracked-files=all | tr '\n' ';')" \
    "$(cksum < "$1/$OVL_FILE")"
}
run_pin() {  # run_pin <repo> args...: prints the exit status
  local repo=$1; shift
  bash "$PIN" --overlay-repo "$repo" --source-repo "$SRC" --file "$OVL_FILE" "$@" \
    > "$WORK/pin.out" 2>&1
  echo $?
}
# expect_unchanged <label> <expected status> <repo> args...
expect_unchanged() {
  local label=$1 want=$2 repo=$3; shift 3
  local before after status
  before="$(snapshot "$repo")"
  status="$(run_pin "$repo" "$@")"
  after="$(snapshot "$repo")"
  ok; [ "$status" = "$want" ] \
    || fail "pin: $label: exit $status, expected $want ($(tr '\n' ' ' < "$WORK/pin.out"))"
  ok; [ "$before" = "$after" ] || fail "pin: $label: repository changed"
}

# Valid forward pin.
status="$(run_pin "$OVL" --tag "$C3" --digest "$D3" --image "$IMAGE")"
ok; if [ "$status" != "0" ]; then
  fail "pin: valid forward pin refused (exit $status: $(tr '\n' ' ' < "$WORK/pin.out"))"
else
  ok; [ "$(git -C "$OVL" rev-list --count "$BASE_HEAD..HEAD")" = "1" ] || fail "pin: forward pin did not make exactly one commit"
  ok; [ "$(git -C "$OVL" diff --name-only "$BASE_HEAD" HEAD)" = "$OVL_FILE" ] || fail "pin: forward pin changed other files"
  ok; [ "$(git -C "$OVL" diff --numstat "$BASE_HEAD" HEAD | cut -f1,2)" = "$(printf '2\t2')" ] \
    || fail "pin: forward pin did not change exactly two lines"
  ok; [ -z "$(git -C "$OVL" diff -U0 "$BASE_HEAD" HEAD | grep -E '^[+-]' | grep -vE '^(\+\+\+|---) ' | grep -vE '^[+-]    (newTag|digest): ')" ] \
    || fail "pin: forward pin changed a line other than newTag or digest"
  ok; [ "$(grep -cxF "    newTag: \"$C3\"" "$OVL/$OVL_FILE")" = "1" ] || fail "pin: new newTag line not present exactly once"
  ok; [ "$(grep -cxF "    digest: $D3" "$OVL/$OVL_FILE")" = "1" ] || fail "pin: new digest line not present exactly once"
  ok; [ "$(git -C "$OVL" log -1 --format=%s)" = "chore(sellbird): pin $C3 $D3" ] || fail "pin: unexpected commit message"
  ok; [ -z "$(git -C "$OVL" status --porcelain)" ] || fail "pin: forward pin left the checkout dirty"
fi
git -C "$OVL" reset -q --hard "$BASE_HEAD"

# Refusals: each leaves the repository unchanged.
expect_unchanged "same tag and digest is a no-op" 3 "$OVL" --tag "$C2" --digest "$D2" --image "$IMAGE"
expect_unchanged "same tag, different digest" 1 "$OVL" --tag "$C2" --digest "$D3"
expect_unchanged "tag-only image (no digest given)" 1 "$OVL" --tag "$C3"
expect_unchanged "tag-only image (empty digest)" 1 "$OVL" --tag "$C3" --digest ""
expect_unchanged "backwards pin" 1 "$OVL" --tag "$C1" --digest "$D3"
expect_unchanged "diverged pin" 1 "$OVL" --tag "$CX" --digest "$D3"
expect_unchanged "malformed digest (63 hex)" 1 "$OVL" --tag "$C3" --digest "sha256:$(printf '%063d' 0)"
expect_unchanged "malformed digest (uppercase)" 1 "$OVL" --tag "$C3" --digest "sha256:$(hex64 A)"
expect_unchanged "malformed digest (wrong algorithm)" 1 "$OVL" --tag "$C3" --digest "sha512:$(hex64 3)"
expect_unchanged "malformed tag (short sha)" 1 "$OVL" --tag "${C3:0:12}" --digest "$D3"
expect_unchanged "unknown commit" 1 "$OVL" --tag "$(printf '%040d' 0 | tr 0 f)" --digest "$D3"
expect_unchanged "wrong image name" 1 "$OVL" --tag "$C3" --digest "$D3" --image "ghcr.io/example-other/sellbird"

printf 'untracked\n' > "$OVL/stray.txt"
expect_unchanged "dirty checkout" 1 "$OVL" --tag "$C3" --digest "$D3"
rm -f "$OVL/stray.txt"

OVL_TAGONLY="$WORK/overlay-tag-only"
make_overlay "$OVL_TAGONLY" "  - name: sellbird" "    newName: $IMAGE" "    newTag: \"$C2\"" || exit 2
expect_unchanged "tag-only image entry in the overlay" 1 "$OVL_TAGONLY" --tag "$C3" --digest "$D3"

OVL_ORDER="$WORK/overlay-order"
make_overlay "$OVL_ORDER" "  - name: sellbird" "    newName: $IMAGE" "    digest: $D2" "    newTag: \"$C2\"" || exit 2
expect_unchanged "entry not in fixed line order" 1 "$OVL_ORDER" --tag "$C3" --digest "$D3"

OVL_EXTRA="$WORK/overlay-extra"
make_overlay "$OVL_EXTRA" "${GOOD_ENTRY[@]}" "  - name: other" "    newTag: \"$C2\"" "    digest: $D2" || exit 2
expect_unchanged "second newTag/digest pair in the file" 1 "$OVL_EXTRA" --tag "$C3" --digest "$D3"

OVL_PLACEHOLDER="$WORK/overlay-placeholder"
make_overlay "$OVL_PLACEHOLDER" "  - name: sellbird" "    newName: $IMAGE" \
  "    newTag: \"0123456789abcdef0123456789abcdef01234567\"" "    digest: $D2" || exit 2
expect_unchanged "pinned SHA not in source history" 1 "$OVL_PLACEHOLDER" --tag "$C3" --digest "$D3"

# ---------------------------------------------------------------------- result
echo "check_manifests: $checks checks, $failures failed"
[ "$failures" -eq 0 ] || exit 1
exit 0
