# Design: Make the Sellbird image reproducible and runnable in Kubernetes

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 6). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Pin the Claude CLI to an exact version with checksum verification instead of an unpinned install script, move writable state to a /data volume so the root filesystem can be read-only, run gateway mode by configuration with a health endpoint reachable from the Service, keep the non-root user, include the Postgres client dependencies, and never log the token. The brain reads CLAUDE_CODE_OAUTH_TOKEN from the environment only (Secret `sellbird-claude`), with no credential written under /data or /home.

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

Changed baseline test files (justified): none yet.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.

## Open Questions

None that change what gets built; the platform contract's operator agreement is tracked as a boundary receipt.
