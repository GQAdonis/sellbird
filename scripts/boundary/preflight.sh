#!/usr/bin/env bash
# Boundary preflight: pull digest-pinned tool images so later boundary scripts
# need nothing installed on the host except Docker. Nothing is installed locally.
#
# Run it:      scripts/boundary/preflight.sh
# Source it:   . scripts/boundary/preflight.sh   (gives the wrapper functions)
#
# Each image is pinned by the digest of its multi-arch index, resolved with
# `docker buildx imagetools inspect <image:tag>`; the tag is kept only as a
# readable label. Bump a pin by re-resolving the digest and editing it here.
set -euo pipefail

SB_ACTIONLINT_IMAGE="rhysd/actionlint:1.7.7@sha256:887a259a5a534f3c4f36cb02dca341673c6089431057242cdc931e9f133147e9"
SB_KUSTOMIZE_IMAGE="registry.k8s.io/kustomize/kustomize:v5.6.0@sha256:b5f56e6becd1ba93a1a775a149763e3841a177beb10191624100bed81b44d297"
SB_YQ_IMAGE="mikefarah/yq:4.45.1@sha256:2c100efaca06e95ffe452cfe9bfc0048b493f0f3a072d5fe06f828c638d9462b"
SB_PG18_IMAGE="postgres:18@sha256:2ea8630df176ad090ec92136dee850397c5af8781e4bcf2e4162593691c61bbc"

# The repository root is mounted read-only at /work; tools run from there.
SB_ROOT="${SB_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

sb_images() {
  printf '%s\n' "$SB_ACTIONLINT_IMAGE" "$SB_KUSTOMIZE_IMAGE" "$SB_YQ_IMAGE" "$SB_PG18_IMAGE"
}

# actionlint [args...]   e.g. actionlint .github/workflows/*.yml
sb_actionlint() {
  docker run --rm -v "$SB_ROOT:/work:ro" -w /work "$SB_ACTIONLINT_IMAGE" "$@"
}

# kustomize build infra/k8s/overlays/example
sb_kustomize() {
  docker run --rm -v "$SB_ROOT:/work:ro" -w /work "$SB_KUSTOMIZE_IMAGE" "$@"
}

# yq '.spec' file.yaml   (reads stdin when given no file: use sb_yq_stdin)
sb_yq() {
  docker run --rm -v "$SB_ROOT:/work:ro" -w /work "$SB_YQ_IMAGE" "$@"
}

sb_yq_stdin() {
  docker run --rm -i "$SB_YQ_IMAGE" "$@"
}

# Postgres 18 client tools, e.g. sb_pg psql "$DSN" -c 'select 1'
#   sb_pg pg_dump --schema-only "$DSN"
# Uses the host network so a DSN pointing at the compose stack's published port works.
sb_pg() {
  docker run --rm -i --network host -v "$SB_ROOT:/work:ro" -w /work "$SB_PG18_IMAGE" "$@"
}

sb_preflight() {
  command -v docker >/dev/null 2>&1 || { echo "preflight: docker is required" >&2; return 1; }
  local image
  while IFS= read -r image; do
    echo "preflight: pulling $image"
    docker pull --quiet "$image" >/dev/null
  done < <(sb_images)
  echo "preflight: ok"
  echo "preflight: wrappers (source this file): sb_actionlint sb_kustomize sb_yq sb_yq_stdin sb_pg"
  echo "preflight: equivalent commands:"
  echo "  docker run --rm -v \"\$PWD:/work:ro\" -w /work $SB_ACTIONLINT_IMAGE <args>"
  echo "  docker run --rm -v \"\$PWD:/work:ro\" -w /work $SB_KUSTOMIZE_IMAGE <args>"
  echo "  docker run --rm -v \"\$PWD:/work:ro\" -w /work $SB_YQ_IMAGE <args>"
  echo "  docker run --rm -i --network host -v \"\$PWD:/work:ro\" -w /work $SB_PG18_IMAGE <psql|pg_dump|pg_restore ...>"
}

# Run the preflight only when executed, not when sourced.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  sb_preflight
fi
