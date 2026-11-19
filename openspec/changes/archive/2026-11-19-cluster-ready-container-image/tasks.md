# Tasks

Model routes for these tasks: see **TASK MODEL ASSIGNMENTS** in `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md`, rows for change `cluster-ready-container-image`.

## 6. Make the Sellbird image reproducible and runnable in Kubernetes

- [x] 6.1 Pin and verify the Claude CLI install and remove the unpinned installer (verify at the phase boundary per the plan's coverage table)
- [x] 6.2 Move writable paths to /data, support read-only root and gateway-mode health checks (verify at the phase boundary per the plan's coverage table)
- [x] 6.3 Add Postgres driver dependencies and image metadata labels (verify at the phase boundary per the plan's coverage table)
- [x] 6.4 Write scripts/boundary/check_container.sh asserting non-root, read-only root, no token or credential in logs or filesystem (verify at the phase boundary per the plan's coverage table)
