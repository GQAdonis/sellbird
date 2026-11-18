# Design: Sellbird's generic manifests, migration job and the digest-pinning deploy bot targeting the platform repo

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 9). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Add infra/k8s base (Deployment with read-only root and non-root securityContext, ServiceAccount, Service, NetworkPolicy allowing only flint-gate, a migration Job running `sellbird storage migrate` with the migration-role Secret, app Secret references by name via secretKeyRef only, including `sellbird-claude`) and an overlays/example overlay using example.test values only. Add the deploy job: after images.yml outputs the digest, it mints a GitHub App token for the platform repository named by a repository variable (no literal), and writes newTag+digest into the overlay path defined by the platform contract, with SHA/digest regex, never-backwards, changed-lines-only and retry guards. Add infra/github/main-ruleset.json (required checks from tests.yml) and CODEOWNERS for this fork. No real hostname or registry literal appears in this repository; the production overlay and the Argo CD AppProject/Application live in the platform repository. Applying settings or anything to the cluster is operator-approved; live sync is gated on the platform phase.

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

Changed baseline test files (justified): none yet.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.

## Open Questions

None that change what gets built; the platform contract's operator agreement is tracked as a boundary receipt.
