#!/usr/bin/env bash
# Verify a downloaded Trivy release archive against the SHA-256 pinned in the
# workflow, before any scan runs.
#
#   scripts/ci/verify-trivy.sh FILE EXPECTED_SHA256
#
# Fails closed: an expected value that is not 64 lowercase hex characters (for
# example the REPLACE_WITH_SHA256_OF_TRIVY_... placeholder) is refused, so the
# workflow cannot scan with an unchecked binary. Exit 0 on a match, 1 on a
# mismatch or a missing file, 2 on bad arguments. (OpenSpec change
# pipeline-hardening, 1.3.)
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $(basename "$0") FILE EXPECTED_SHA256" >&2
  exit 2
fi
file="$1"
expected="$2"

if [[ ! "$expected" =~ ^[0-9a-f]{64}$ ]]; then
  echo "verify-trivy: the pinned SHA-256 is not set (got a placeholder or a malformed value)." >&2
  echo "verify-trivy: set it from the official Trivy checksums file for this version; see the workflow comment." >&2
  exit 2
fi
if [[ ! -f "$file" ]]; then
  echo "verify-trivy: $file does not exist" >&2
  exit 1
fi

if command -v sha256sum > /dev/null 2>&1; then
  actual="$(sha256sum "$file" | cut -d' ' -f1)"
else
  actual="$(shasum -a 256 "$file" | cut -d' ' -f1)"
fi

if [[ "$actual" != "$expected" ]]; then
  echo "verify-trivy: MISMATCH $file has SHA-256 $actual, pinned $expected" >&2
  exit 1
fi
echo "verify-trivy: $(basename "$file") matches the pinned SHA-256."
