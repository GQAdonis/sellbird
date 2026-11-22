## Why

A red test run does not stop a deploy; the image ID that publish trusts is read after third-party scans ran; the Trivy binary is unchecked; dependencies install from ranges without hashes; no failing scan has ever been shown to stop a release.

## What Changes

- Make tests.yml callable (`workflow_call`), call it from images.yml and make the deploy job need it.
- Record the image ID and save the image tar immediately after the build step; after all scans recompute the ID and fail on mismatch; publish from the saved tar.
- Pin a SHA-256 for the Trivy binary in the workflow and verify it before any scan.
- Add workflow_dispatch control inputs `failing-test` and `vulnerable-image` that run the real gates and can never publish or deploy.
- Generate a tracked requirements.lock with hashes for linux amd64 and arm64 using uv; install it with --require-hashes in the Dockerfile; fail CI when the lock is stale.

## Impact

- Affected capability: `delivery-pipeline`
- Files: .github/workflows/**; .github/workflows/**, scripts/ci/**; .github/workflows/images.yml; .github/workflows/images.yml, scripts/ci/**; Dockerfile, requirements.lock, .github/workflows/**, scripts/ci/**
- Phase: `sellbird-go-live`; verified once at the phase boundary, not per task.
