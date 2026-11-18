# Hosting documentation, changelog and the independent security review

## Why

Write docs/hosting.md using example.test values only (gateway mode, Postgres backend, move tool, deployment, operator steps) and the CHANGELOG entry. This change serves phase goal G6 (restated) of KBD phase `postgres-gke-deployment`.

## What Changes

Write docs/hosting.md using example.test values only (gateway mode, Postgres backend, move tool, deployment, operator steps) and the CHANGELOG entry. The security-reviewer role, in a separate read-only context, reviews storage, auth, gateway config, manifests, workflows and ruleset after implementation and records severity-ranked findings under .agent-team/findings/security/; CRITICAL or HIGH findings block closure.

## Capabilities

- None. This change alters no spec-level behaviour (`skip_specs: true`); it is tooling, configuration or documentation verified by boundary scenarios.

## Impact

- Scope: docs | review
- Depends on: baseline-test-green, platform-interface-contract, postgres-storage-backend, hosted-gateway-mode, sqlite-to-postgres-move-tool, sellbird-gateway-route-config, cluster-ready-container-image, image-build-scan-publish, gitops-deploy-sellbird
- Owner role: `documentation-specialist`
- Plan: `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md` (change 10)
