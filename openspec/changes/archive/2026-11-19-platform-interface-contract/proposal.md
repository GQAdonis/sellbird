# Agree the interface between Sellbird and the shared platform (G7)

## Why

Write docs/platform-interface.md and an OpenSpec capability spec defining what Sellbird needs from the shared platform: how the sellbird database and its least-privilege roles are provisioned on the shared flint-forge PG18, the flint-gate issuer, JWKS URL and minted-claims shape (aud=sellbird, sub=Kratos identity id), the hostname listener and certificate ownership on the shared Gateway, namespaces and secret names, and Kratos operator-identity provisioning. This change serves phase goal G7 of KBD phase `postgres-gke-deployment`.

## What Changes

Write docs/platform-interface.md and an OpenSpec capability spec defining what Sellbird needs from the shared platform: how the sellbird database and its least-privilege roles are provisioned on the shared flint-forge PG18, the flint-gate issuer, JWKS URL and minted-claims shape (aud=sellbird, sub=Kratos identity id), the hostname listener and certificate ownership on the shared Gateway, namespaces and secret names, and Kratos operator-identity provisioning. Mark it as the counterpart the new platform repository must satisfy; agreement is recorded by the operator. It also fixes the AI brain credential contract: the operator creates Secret `sellbird-claude` with key `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`, decision D4), consumed only as an environment variable, never written to disk or logged. Per operator decision (2026-11-18), Sellbird's production overlay, real hostname and digest pins live in the platform repository (which can be private), not in this public fork; the contract defines the overlay path there, the pin format the deploy bot writes, the Argo CD AppProject/Application ownership, and the repository variable naming the platform repo.

## Capabilities

- **New Capabilities**: `platform-interface` — Defines what Sellbird requires from the shared platform so the two repositories can be built and verified independently.
- **Modified Capabilities**: none

## Impact

- Scope: docs | spec
- Depends on: none
- Owner role: `architect`
- Plan: `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md` (change 2)
