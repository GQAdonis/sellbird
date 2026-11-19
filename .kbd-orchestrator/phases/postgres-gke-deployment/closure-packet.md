# Closure packet — postgres-gke-deployment

Disposition: **CLOSED** (budget-exhausted). This packet is a derived view of
the bound contract (sha256:7d8112c02343cc0118a315dea16d8f75d3ad05eea1a31bf8c220b4e320cfff53) and
`boundary-results.json` (sha256:c5381fb8b667df693c8d18dce879137594acb9c71e578aa0f94773df12966342); the canonical KBD disposition is authoritative.

## What works, and for whom

- SCN-BASE-001 — The configured test command runs and every baseline test still passes, with only justified test-file changes (for Contributor running the project test command)
- SCN-STORE-001 — State operations on SQLite return the same results as before (for Local single-user operator)
- SCN-STORE-002 — State operations on Postgres 18 behave exactly like SQLite, including signal governance (for Hosted operator)
- SCN-STORE-003 — Schema changes can be undone and the running app cannot alter the schema (for Hosted operator upgrading or rolling back)
- SCN-SEND-001 — An approved email is sent exactly once even when the heartbeat and dashboard race (for A prospect receiving outreach)
- SCN-SEND-002 — Quiet hours, daily limit, opt-out and approval ladder behave the same on both backends (for A prospect and the sender's domain reputation)
- SCN-MOVE-001 — An existing SQLite database lands in Postgres with nothing lost (for An operator moving from local to hosted)
- SCN-AUTH-001 — The operator gets in through Kratos and flint-gate; nobody else gets anything (for The operator signing in)
- SCN-AUTH-002 — Local installs keep the token link and refuse public binds (for Local single-user operator)
- SCN-LOG-001 — Neither the dashboard token nor the Claude credential leaks, and the runtime is non-root and read-only (for An operator whose cluster logs are widely readable)
- SCN-BRAIN-001 — The brain authenticates from the Secret-provided variable without persisting it (for The operator running the hosted brain)
- SCN-SHIP-001 — A merge produces a scanned image and a guarded pin with no real hostname in this fork (for The operator shipping a release)
- SCN-CONTRACT-001 — Both repositories can build against one agreed interface (for The platform repository's maintainers)

## Under which conditions

- environment: local: macOS, Linux and Windows with SQLite (CI matrix)
- environment: hosted path: Linux container with Postgres 18 (flint-forge image), Ory Kratos and flint-gate, verified via local Docker stand-ins
- environment: Postgres contract tests: Linux
- SCN-BASE-001 real collaborator: project virtualenv
- SCN-BASE-001 real collaborator: pytest
- SCN-BASE-001 real collaborator: SQLite on disk
- SCN-STORE-001 real collaborator: SQLite on disk
- SCN-STORE-002 real collaborator: flint-forge Postgres 18 container
- SCN-STORE-002 real collaborator: psycopg 3
- SCN-STORE-003 real collaborator: flint-forge Postgres 18 container
- SCN-STORE-003 real collaborator: pg_dump 18
- SCN-SEND-001 real collaborator: flint-forge Postgres 18 container
- SCN-SEND-001 real collaborator: asyncio concurrent connections
- SCN-SEND-002 real collaborator: SQLite on disk
- SCN-SEND-002 real collaborator: flint-forge Postgres 18 container
- SCN-MOVE-001 real collaborator: SQLite on disk
- SCN-MOVE-001 real collaborator: flint-forge Postgres 18 container
- SCN-AUTH-001 real collaborator: sellbird:boundary container
- SCN-AUTH-001 real collaborator: Ory Kratos container
- SCN-AUTH-001 real collaborator: flint-gate container
- SCN-AUTH-001 real collaborator: flint-forge Postgres 18 container
- SCN-AUTH-002 real collaborator: uvicorn dashboard on loopback
- SCN-LOG-001 real collaborator: sellbird:boundary image
- SCN-LOG-001 real collaborator: running compose container
- SCN-BRAIN-001 real collaborator: sellbird:boundary container
- SCN-BRAIN-001 real collaborator: claude CLI subprocess
- SCN-SHIP-001 real collaborator: kustomize
- SCN-SHIP-001 real collaborator: actionlint
- SCN-SHIP-001 real collaborator: deploy guard script
- SCN-SHIP-001 real collaborator: scratch git repository
- SCN-CONTRACT-001 real collaborator: contract check script
- SCN-SEND-002 SUBSTITUTED boundary (not a real claim): the outbound mailbox is a recording test double; no email leaves the machine
- SCN-BRAIN-001 SUBSTITUTED boundary (not a real claim): no real inference call unless the operator supplies a token; without it that sub-check is BLOCKED
- SCN-SHIP-001 SUBSTITUTED boundary (not a real claim): the platform repository is replaced by a scratch fixture repository; live run and Argo CD sync are NOT_EXERCISED (carried CG-1)

## Limits

- SCN-BASE-001: does not prove performance on production hardware
- SCN-STORE-001: does not cover the dashboard UI
- SCN-STORE-002: single-node Postgres only
- SCN-STORE-003: does not test data-preserving down migrations beyond schema
- SCN-SEND-001: concurrency is simulated in one host, not across pods
- SCN-SEND-002: real mailbox delivery is not exercised
- SCN-MOVE-001: the operator's real database is not moved
- SCN-AUTH-001: the public hostname and TLS are not exercised (carried CG-2)
- SCN-AUTH-002: does not exercise MCP agent clients
- SCN-LOG-001: cluster log pipeline itself not exercised
- SCN-BRAIN-001: provider terms for headless subscription use are the operator's risk and are not tested
- SCN-SHIP-001: no real GitHub Actions run, registry push or cluster sync
- SCN-CONTRACT-001: agreement by the platform repository's own phase is outside this contract
- unknown: Live GKE cluster contents (gcloud authentication expired)
- unknown: Whether provider terms allow headless subscription use of the Claude CLI (operator risk)
- unknown: Real-world claim contention rates on Postgres
- unknown: Whether the platform repository exists by closure

## What remains

- nothing: every scenario passed

## Pre-authorization runner artifacts

- none found (90 runner artifact(s) under .kbd-orchestrator/phases/postgres-gke-deployment/evidence/**, all modified at or after the B4 authorization at 2026-11-18T20:14:20.120Z)

This scan is passive evidence (VLBV 04, 10): it reports and never blocks.

## Closure states

| State | Value |
|---|---|
| Implementation complete | true |
| Behavior accepted | true |
| Release eligible | true |
| Release authorized | false (a separate owner decision) |

Method: VLBV.
Executed by: Claude Code (desktop app) unknown (claude-opus-5-5).
