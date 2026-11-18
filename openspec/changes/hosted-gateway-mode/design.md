# Design: Hosted gateway mode: trust a flint-gate JWT, keep local token mode unchanged

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 4). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Add a config-selected gateway mode (never chosen by request headers) that allows a non-loopback bind, accepts the configured public Host and https Origin, verifies the gate-minted JWT against a pinned JWKS (iss, aud, kid, alg, exp) and an allowlisted Kratos sub, maps it to principal user, ignores cookies and unverified x-flint-*/forwarded headers, disables the agent token, and never prints the dashboard token. Local token mode stays the default and still refuses non-loopback binds.

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

Changed baseline test files (justified): none yet.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.

## Open Questions

None that change what gets built; the platform contract's operator agreement is tracked as a boundary receipt.
