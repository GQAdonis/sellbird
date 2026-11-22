#!/usr/bin/env bash
# SCN-PIPE-002 negative control (b): scripts/ci/recheck-image.sh run locally after the saved image is
# swapped for a different one must exit non-zero and report the ID mismatch. Local Docker only; two
# tiny `FROM scratch` images (no pull, no network) are built, and removed afterwards. Steps:
#   1. image A is built; its ID and the SHA-256 of its `docker save` archive are recorded
#      (what the workflow records after the build); the recheck passes (control is not always-failing);
#   2. the ref is moved to a different image B and the archive replaced by B's: the recheck must
#      exit non-zero reporting "MISMATCH image ID" (and the archive mismatch);
#   3. only the archive replaced: it must report "MISMATCH archive SHA-256".
# Packet:  neg-image-swap.sh SCN-PIPE-002
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin negativeControl SCN-PIPE-002
cd "$GOLIVE_ROOT"

golive_require_tools docker
golive_scratch_new
tmp="$GOLIVE_LAST_SCRATCH"
ref="golive-swap:control"
GOLIVE_DOCKER_IMAGES+=("$ref")
build() { printf 'FROM scratch\nLABEL golive.swap=%s\n' "$1" | DOCKER_BUILDKIT=1 docker build -q -t "$2" - > /dev/null; }
rc_of() { local r=0; "$@" > "$tmp/out" 2>&1 || r=$?; echo "$r"; }

build a "$ref" || golive_finish BLOCKED "could not build the scratch control image"
id_a="$(docker image inspect --format '{{.Id}}' "$ref")"
GOLIVE_DOCKER_IMAGES+=("$id_a")
docker save -o "$tmp/image.tar" "$ref"
sha_a="$(golive_sha256 "$tmp/image.tar")"
recheck() { bash "$GOLIVE_ROOT/scripts/ci/recheck-image.sh" "$id_a" "$sha_a" "$ref" "$tmp/image.tar"; }

rc="$(rc_of recheck)"
if [ "$rc" != 0 ]; then
  golive_finish FAIL "the recheck rejected the UNCHANGED image (exit $rc)"
fi

# Variant 2: image and archive both swapped for image B.
build b golive-swap:other || golive_finish BLOCKED "could not build the second control image"
GOLIVE_DOCKER_IMAGES+=("golive-swap:other")
docker tag golive-swap:other "$ref"
docker save -o "$tmp/image.tar" "$ref"
rc="$(rc_of recheck)"
if [ "$rc" = 0 ]; then
  golive_finish FAIL "the recheck ACCEPTED a swapped image"
fi
if ! grep -q 'MISMATCH image ID' "$tmp/out"; then
  golive_finish FAIL "the recheck exited $rc but did not report an image ID mismatch"
fi
golive_note "swapped image rejected with exit $rc, reporting the image ID mismatch"

# Variant 3: engine image restored to A's content, only the archive replaced.
docker tag "$id_a" "$ref"
docker save -o "$tmp/image.tar" "$ref"
sha_a="$(golive_sha256 "$tmp/image.tar")"  # a fresh save of A is the new recorded archive
rc="$(rc_of recheck)"
if [ "$rc" != 0 ]; then
  golive_finish FAIL "could not restore image A for variant 3 (recheck exit $rc)"
fi
docker save -o "$tmp/image.tar" golive-swap:other
rc="$(rc_of recheck)"
if [ "$rc" = 0 ] || ! grep -q 'MISMATCH archive SHA-256' "$tmp/out"; then
  golive_finish FAIL "a replaced archive was not rejected with an archive mismatch (exit $rc)"
fi
golive_finish PASS "swapped image and swapped archive both rejected (non-zero) with the mismatch named; the unchanged image passes"
