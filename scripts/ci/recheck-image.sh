#!/usr/bin/env bash
# Confirm that the image the scans looked at is still the image recorded right
# after the build, and that the saved archive publish will load is unchanged.
#
#   scripts/ci/recheck-image.sh EXPECTED_IMAGE_ID EXPECTED_TAR_SHA256 IMAGE_REF TAR_PATH
#
#   EXPECTED_IMAGE_ID    sha256:<64 hex>, read with `docker image inspect` right after the build
#   EXPECTED_TAR_SHA256  <64 hex>, sha256 of the `docker save` archive written at the same time
#   IMAGE_REF            the image reference in the local Docker engine
#   TAR_PATH             the saved archive
#
# Exit 0 when both match. Exit 1 naming each mismatch (the image in the
# engine, the archive, or both). Exit 2 on bad arguments. Prints only image IDs
# and digests, which are not secret. (OpenSpec change pipeline-hardening, 1.2.)
set -euo pipefail

usage() {
  echo "usage: $(basename "$0") EXPECTED_IMAGE_ID EXPECTED_TAR_SHA256 IMAGE_REF TAR_PATH" >&2
  exit 2
}

[[ $# -eq 4 ]] || usage
expected_id="$1"
expected_tar="$2"
ref="$3"
tar_path="$4"

[[ "$expected_id" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "recheck: expected image ID is malformed" >&2; usage; }
[[ "$expected_tar" =~ ^[0-9a-f]{64}$ ]] || { echo "recheck: expected archive SHA-256 is malformed" >&2; usage; }
[[ -n "$ref" ]] || { echo "recheck: image reference is empty" >&2; usage; }

sha256_of() {
  if command -v sha256sum > /dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

failed=0

if actual_id="$(docker image inspect --format '{{.Id}}' "$ref" 2> /dev/null)"; then
  if [[ "$actual_id" != "$expected_id" ]]; then
    echo "recheck: MISMATCH image ID: $ref is now $actual_id, recorded after build $expected_id" >&2
    failed=1
  fi
else
  echo "recheck: MISMATCH image ID: $ref is no longer in the local Docker engine (recorded $expected_id)" >&2
  failed=1
fi

if [[ -f "$tar_path" ]]; then
  actual_tar="$(sha256_of "$tar_path")"
  if [[ "$actual_tar" != "$expected_tar" ]]; then
    echo "recheck: MISMATCH archive SHA-256: $tar_path is now $actual_tar, recorded after build $expected_tar" >&2
    failed=1
  fi
else
  echo "recheck: MISMATCH archive SHA-256: $tar_path is missing (recorded $expected_tar)" >&2
  failed=1
fi

if [[ "$failed" -ne 0 ]]; then
  exit 1
fi
echo "recheck: $ref is still $expected_id and the saved archive is unchanged ($expected_tar)."
