# Sellbird's generic manifests, migration job and the digest-pinning deploy bot targeting the platform repo

## Why

Add infra/k8s base (Deployment with read-only root and non-root securityContext, ServiceAccount, Service, NetworkPolicy allowing only flint-gate, a migration Job running `sellbird storage migrate` with the migration-role Secret, app Secret references by name via secretKeyRef only, including `sellbird-claude`) and an overlays/example overlay using example.test values only. This change serves phase goal G4 and G6 (restated) of KBD phase `postgres-gke-deployment`.

## What Changes

Add infra/k8s base (Deployment with read-only root and non-root securityContext, ServiceAccount, Service, NetworkPolicy allowing only flint-gate, a migration Job running `sellbird storage migrate` with the migration-role Secret, app Secret references by name via secretKeyRef only, including `sellbird-claude`) and an overlays/example overlay using example.test values only. Add the deploy job: after images.yml outputs the digest, it mints a GitHub App token for the platform repository named by a repository variable (no literal), and writes newTag+digest into the overlay path defined by the platform contract, with SHA/digest regex, never-backwards, changed-lines-only and retry guards. Add infra/github/main-ruleset.json (required checks from tests.yml) and CODEOWNERS for this fork. No real hostname or registry literal appears in this repository; the production overlay and the Argo CD AppProject/Application live in the platform repository. Applying settings or anything to the cluster is operator-approved; live sync is gated on the platform phase.

## Capabilities

- **New Capabilities**: `image-delivery` — Delivers a published image to the platform's overlay by pinned digest with guards.
- **Modified Capabilities**: none

## Impact

- Scope: infra | ci
- Depends on: platform-interface-contract, sellbird-gateway-route-config, image-build-scan-publish
- Owner role: `platform-engineer`
- Plan: `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md` (change 9)
