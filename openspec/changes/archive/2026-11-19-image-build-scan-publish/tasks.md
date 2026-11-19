# Tasks

Model routes for these tasks: see **TASK MODEL ASSIGNMENTS** in `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md`, rows for change `image-build-scan-publish`.

## 8. Build, scan and publish the image to GHCR by digest on merge to main

- [x] 8.1 Author images.yml build, non-root check and push-by-SHA with digest outputs (verify at the phase boundary per the plan's coverage table)
- [x] 8.2 Add vulnerability scan and secret scan with a negative control (verify at the phase boundary per the plan's coverage table)
- [x] 8.3 Add a Postgres 18 service-container job to tests.yml for the storage contract tests and name the required checks (verify at the phase boundary per the plan's coverage table)
