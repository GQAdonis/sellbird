## 1. Gate deploys on tests, trust the scanned image, lock dependencies

- [x] 1.1 Make tests.yml callable (`workflow_call`), call it from images.yml and make the deploy job need it (role: platform-engineer)
- [x] 1.2 Record the image ID and save the image tar immediately after the build step; after all scans recompute the ID and fail on mismatch; publish from the saved tar (role: platform-engineer)
- [x] 1.3 Pin a SHA-256 for the Trivy binary in the workflow and verify it before any scan (role: platform-engineer)
- [x] 1.4 Add workflow_dispatch control inputs `failing-test` and `vulnerable-image` that run the real gates and can never publish or deploy (role: platform-engineer)
- [x] 1.5 Generate a tracked requirements.lock with hashes for linux amd64 and arm64 using uv; install it with --require-hashes in the Dockerfile; fail CI when the lock is stale (role: platform-engineer)
