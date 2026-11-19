# ADR 0001: Shared platform services and Sellbird's single-tenant database

## Status

Accepted (2026-11-19). Proposed on 2026-11-18. The operator recorded agreement
with the platform interface contract (`docs/platform-interface.md`) in the shared
platform repository's phase: version 1, then version 2, which changes only operator
identity provisioning.

## Context

Sellbird is a single-user, local-first app: state in SQLite behind
`sellbird/storage.py`, a loopback-only FastAPI dashboard unlocked by a token link.
Phase `postgres-gke-deployment` adds a hosted deployment on GKE, signed in through
Ory Kratos and flint-gate, with state on Postgres 18 built from the flint-forge
image.

The operator decided (assessment decisions D1 to D12) that:

- Postgres, Kratos, flint-gate, Hydra, flint-realtime-fabric, ElectricSQL and the
  Envoy Gateway are shared by several applications, so they belong in a new,
  separate platform repository with its own Argo CD projects and its own phase
  (D2, D5, D8, D9, D10).
- Sellbird gets its own database and least-privilege roles on the shared Postgres,
  not its own Postgres server (D2).
- Sign-in is operator-only with a second factor; flint-gate checks the Kratos
  session and Sellbird accepts only an allowlisted identity (D3, D6, D11).
- flint-gate is used as it is today, with no changes to its repository (D6). Its
  minted token has no default `aud` and it forwards browser cookies upstream.
- This repository is a public fork. Real hostnames, registry accounts and the
  production overlay must not be in it (plan-stage decision, 2026-11-18).
- The tenancy question (one Sellbird workspace per database, or row-level security
  inside one database) was open at assessment; at plan the operator chose single
  tenant with RLS deferred.

Two repositories built in parallel need one written interface, or each will guess
the other's names, ports, claims and paths.

## Decision

1. **Shared services live in the platform repository.** Sellbird consumes them
   through `docs/platform-interface.md`, which names every database object, role,
   Secret and key, namespace, port, claim, URL shape and overlay path that crosses
   the boundary. Changing any of them bumps the contract version and needs a new
   operator agreement.
2. **One `sellbird` database, single tenant, two roles.** The platform creates
   database `sellbird` owned by `sellbird_migrate` (which runs migrations and owns
   every object) and a runtime role `sellbird_app` with only `SELECT`, `INSERT`,
   `UPDATE`, `DELETE`, sequence use and function execution through default
   privileges. No DDL at runtime, no extensions, no row-level security. Isolation
   from other applications is by database and role.
3. **flint-gate's minted token is Sellbird's only hosted credential.** The route
   adds `aud: sellbird` (and `aal`) through `additional_claims`; the platform keeps
   the TTL at 300 s or less and signs with RS256. Sellbird verifies `iss`, `aud`,
   `kid`, `alg`, `exp` against a JWKS fetched only from a configured in-cluster URL,
   allowlists `sub`, and ignores cookies and every forwarded or `x-flint-*` header.
4. **The production overlay and image pins live in the platform repository.**
   This repository ships a hostname-free base and an `example.test` overlay. The
   deploy bot writes only `newTag` and `digest` into
   `apps/sellbird/overlays/production/kustomization.yaml` in the repository named
   by the `SELLBIRD_PLATFORM_REPO` variable.
5. **Secrets are created by the operator by hand**, referenced by name only, and
   never managed by Argo CD. The AI credential is Secret `sellbird-claude`, key
   `CLAUDE_CODE_OAUTH_TOKEN`, consumed only as an environment variable.

## Alternatives considered

- **A Postgres server per application.** Strongest isolation and independent
  upgrades, but one more stateful service to run, back up and patch for a
  single-user app, and it contradicts D2. Rejected.
- **One shared database with a schema per application.** Fewer databases, but
  cross-application grants and `search_path` mistakes become possible, and the
  flint-forge image's preloaded extensions are configured for the `flint` database.
  Rejected in favour of a database per application.
- **Row-level security inside `sellbird` now.** Would prepare for several
  workspaces or users, which this phase excludes. RLS policies on every table add
  migration and test surface with nothing to protect yet. Deferred until a
  multi-tenant requirement exists; adding it later is a migration plus a contract
  version bump.
- **Trusting flint-gate's `x-flint-*` identity headers.** Simpler, but a header is
  only as trustworthy as every hop that can set it, and gateway mode must not depend
  on network position alone. Rejected; the signed token is required.
- **Keeping the production overlay in this repository.** Simplest for the deploy
  bot, but it publishes the real hostname and pins in a public fork. Rejected by the
  operator.
- **Changing flint-gate to add a default audience and strip cookies.** Cleaner, but
  out of scope (D6). Revisit in the platform phase.

## Consequences

- Sellbird's hosted work (storage backend, gateway mode, manifests, deploy bot) can
  be built and verified here against local stand-ins before the platform exists.
  The live parts wait for the platform phase (carried goals CG-1 to CG-3).
- The platform repository must provision the database and roles, the Kratos
  settings, flint-gate's issuer, TTL and JWKS, the Gateway listener and certificate,
  the AppProject and Application, and the NetworkPolicy allowances exactly as the
  contract says. Its own phase verifies that.
- The runtime role cannot repair a schema mismatch; migrations run as a separate
  PreSync Job with the migration role, and a failed migration blocks the sync.
- A shared Postgres is a shared failure and noisy-neighbour domain. Connection
  limits and statement timeouts on Sellbird's roles bound Sellbird's share; backups
  and HA are deferred (D12).
- Kratos's parent-domain session cookie reaches every host under that domain; each
  must sit behind flint-gate or ignore it.
- A minted token stays valid for up to 300 s after access is revoked.
- Multi-tenant or multi-user Sellbird needs a new ADR, RLS or per-tenant databases,
  and a contract version bump.
