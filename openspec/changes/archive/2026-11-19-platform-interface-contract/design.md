# Design: Agree the interface between Sellbird and the shared platform (G7)

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 2). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Write docs/platform-interface.md and an OpenSpec capability spec defining what Sellbird needs from the shared platform: how the sellbird database and its least-privilege roles are provisioned on the shared flint-forge PG18, the flint-gate issuer, JWKS URL and minted-claims shape (aud=sellbird, sub=Kratos identity id), the hostname listener and certificate ownership on the shared Gateway, namespaces and secret names, and Kratos operator-identity provisioning. Mark it as the counterpart the new platform repository must satisfy; agreement is recorded by the operator. It also fixes the AI brain credential contract: the operator creates Secret `sellbird-claude` with key `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`, decision D4), consumed only as an environment variable, never written to disk or logged. Per operator decision (2026-11-18), Sellbird's production overlay, real hostname and digest pins live in the platform repository (which can be private), not in this public fork; the contract defines the overlay path there, the pin format the deploy bot writes, the Argo CD AppProject/Application ownership, and the repository variable naming the platform repo.

### Design notes (architect, 2026-11-18)

- The contract is `docs/platform-interface.md`, contract version 1. Its 22 required headings are the required-section list in `specs/platform-interface/spec.md`; `scripts/boundary/check_platform_contract.sh` checks them and the names inside. The rationale is ADR 0001 (`docs/adr/0001-shared-platform-and-single-tenant-database.md`).
- Database: two login roles only. `sellbird_migrate` owns the `sellbird` database and so its `public` schema and every object; `sellbird_app` gets DML, sequence use and EXECUTE through `ALTER DEFAULT PRIVILEGES FOR ROLE sellbird_migrate`. No separate NOLOGIN owner role, no schema other than `public`, no extensions: the smallest arrangement that keeps the runtime role free of DDL. Both Secrets use the same key, `SELLBIRD_DATABASE_URL`, so the app and the migration Job read one variable from different Secrets.
- Token: flint-gate's minted JWT is forwarded as `Authorization: Bearer` (flint-gate `pipeline.rs`). It has no default `aud` and merges identity traits into the payload (`jwt_mint.rs`), so the route sets `aud: sellbird` and `aal` through `additional_claims`, and the identity schema must not use reserved claim names as traits. TTL comes from flint-gate's global `jwt.default_ttl_seconds`, which the platform keeps at 300 or less. The JWKS is flint-gate's `/.well-known/jwks.json` on its proxy port 4456, fetched in-cluster only from configuration, with bounded refresh.
- aal2 is enforced by Kratos (`session.whoami.required_aal: highest_available`, registration and recovery disabled), so flint-gate never authenticates an aal1 session. Sellbird checking the minted `aal` claim is defence in depth, left as a SHOULD (open question 4).
- Hostnames: Kratos's public API and login UI sit on a platform auth host with a parent-domain session cookie, so one shared Kratos serves several application hosts. Sellbird's flint-gate site has no anonymous routes; the real hostname is substituted by the platform overriding only `sites[].domains`.
- Overlay: the deploy bot edits only `newTag` and `digest` of the `sellbird` images entry in `apps/sellbird/overlays/production/kustomization.yaml` in the repository named by `SELLBIRD_PLATFORM_REPO`. The overlay pulls Sellbird's base as a remote base pinned to a commit SHA, moved only by reviewed pull requests.
- Migrations run as an Argo CD PreSync Job with the migration Secret; a failed migration blocks the sync and leaves the previous image running.

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

Changed baseline test files (justified): none yet.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.

## Open Questions

The platform contract's operator agreement is tracked as a boundary receipt (SCN-CONTRACT-001 stays BLOCKED without it). Questions the operator answers when agreeing; each has a default already written into the contract:

1. Kratos host and cookie: shared auth host with a parent-domain cookie (default), or Kratos self-service proxied on Sellbird's own host with a host-only cookie (the local stand-in in `sellbird-gateway-route-config` may use this shape).
2. Deploy App installation: the App now writes to the platform repository, not this fork. Install it only on the platform repository (default)?
3. Postgres TLS inside the cluster: `sslmode=require` (default) or `verify-full` with a platform CA.
4. Should hosted-gateway-mode also reject tokens whose `aal` is not `aal2`? Needs a spec change in that change, owned by the identity engineer.
5. Kratos recovery disabled, with recovery only through the admin API (default)?
6. Platform namespace names and pod labels (`flint-gate`, `ory`, `flint-forge`, `argocd`; `app.kubernetes.io/name: flint-gate` and `flint-forge-postgres`): confirm, since Sellbird's NetworkPolicy hard-codes them.
7. Email provider OAuth tokens Sellbird stores at runtime (for example a Gmail refresh token) are out of scope for this contract: acceptable for this phase?
