# Design: Build, scan and publish the image to GHCR by digest on merge to main

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 8). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Add .github/workflows/images.yml following the github-argocd-continuous-deployment reference pattern: build with buildx, a non-root check, a vulnerability scan with a fail threshold on CRITICAL, an artifact secret scan with a planted-secret negative control that must fail, refuse to push if the SHA tag already exists, push ghcr.io/gqadonis/sellbird:<sha>, and expose the digest as a job output. paths-ignore the overlay so the bot's pin commit does not rebuild.

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

Changed baseline test files (justified): none yet.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.

## Open Questions

None that change what gets built; the platform contract's operator agreement is tracked as a boundary receipt.
