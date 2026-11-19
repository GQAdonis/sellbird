# Design: Hosting documentation, changelog and the independent security review

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 10). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Write docs/hosting.md using example.test values only (gateway mode, Postgres backend, move tool, deployment, operator steps) and the CHANGELOG entry. The security-reviewer role, in a separate read-only context, reviews storage, auth, gateway config, manifests, workflows and ruleset after implementation and records severity-ranked findings under .agent-team/findings/security/; CRITICAL or HIGH findings block closure.

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

Changed baseline test files (justified): none yet.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.

## Open Questions

None that change what gets built; the platform contract's operator agreement is tracked as a boundary receipt.
