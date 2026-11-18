# Tasks

Model routes for these tasks: see **TASK MODEL ASSIGNMENTS** in `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md`, rows for change `gitops-deploy-sellbird`.

## 9. Sellbird's generic manifests, migration job and the digest-pinning deploy bot targeting the platform repo

- [x] 9.1 Author infra/k8s base and an example.test overlay with NetworkPolicy, read-only root and secretKeyRef-only secrets (verify at the phase boundary per the plan's coverage table)
- [x] 9.2 Author the migration Job using the migration-role Secret and order it before the Deployment (verify at the phase boundary per the plan's coverage table)
- [x] 9.3 Add the deploy job: GitHub App token for the platform repo, digest pin into its overlay, guards and push retry (verify at the phase boundary per the plan's coverage table)
- [x] 9.4 Author infra/github/main-ruleset.json, CODEOWNERS and the operator runbook for settings (verify at the phase boundary per the plan's coverage table)
- [x] 9.5 Write scripts/boundary/check_manifests.sh asserting image@sha256 pinning, NetworkPolicy, read-only root, migration Job, secretKeyRef-only secrets and no real hostname literal (verify at the phase boundary per the plan's coverage table)
