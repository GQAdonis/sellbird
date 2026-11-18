# Design: Agree the interface between Sellbird and the shared platform (G7)

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 2). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Write docs/platform-interface.md and an OpenSpec capability spec defining what Sellbird needs from the shared platform: how the sellbird database and its least-privilege roles are provisioned on the shared flint-forge PG18, the flint-gate issuer, JWKS URL and minted-claims shape (aud=sellbird, sub=Kratos identity id), the hostname listener and certificate ownership on the shared Gateway, namespaces and secret names, and Kratos operator-identity provisioning. Mark it as the counterpart the new platform repository must satisfy; agreement is recorded by the operator. It also fixes the AI brain credential contract: the operator creates Secret `sellbird-claude` with key `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`, decision D4), consumed only as an environment variable, never written to disk or logged. Per operator decision (2026-11-18), Sellbird's production overlay, real hostname and digest pins live in the platform repository (which can be private), not in this public fork; the contract defines the overlay path there, the pin format the deploy bot writes, the Argo CD AppProject/Application ownership, and the repository variable naming the platform repo.

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

Changed baseline test files (justified): none yet.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.

## Open Questions

None that change what gets built; the platform contract's operator agreement is tracked as a boundary receipt.
