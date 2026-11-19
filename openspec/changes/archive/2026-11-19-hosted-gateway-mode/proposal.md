# Hosted gateway mode: trust a flint-gate JWT, keep local token mode unchanged

## Why

Add a config-selected gateway mode (never chosen by request headers) that allows a non-loopback bind, accepts the configured public Host and https Origin, verifies the gate-minted JWT against a pinned JWKS (iss, aud, kid, alg, exp) and an allowlisted Kratos sub, maps it to principal user, ignores cookies and unverified x-flint-*/forwarded headers, disables the agent token, and never prints the dashboard token. This change serves phase goal G5 (restated) of KBD phase `postgres-gke-deployment`.

## What Changes

Add a config-selected gateway mode (never chosen by request headers) that allows a non-loopback bind, accepts the configured public Host and https Origin, verifies the gate-minted JWT against a pinned JWKS (iss, aud, kid, alg, exp) and an allowlisted Kratos sub, maps it to principal user, ignores cookies and unverified x-flint-*/forwarded headers, disables the agent token, and never prints the dashboard token. Local token mode stays the default and still refuses non-loopback binds.

## Capabilities

- **New Capabilities**: `dashboard-gateway-mode` — Lets the dashboard run behind flint-gate on a public hostname while keeping the local single-user token mode unchanged.
- **Modified Capabilities**: none

## Impact

- Scope: api | auth | cli
- Depends on: platform-interface-contract
- Owner role: `identity-engineer`
- Plan: `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md` (change 4)
