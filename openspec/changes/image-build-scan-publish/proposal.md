# Build, scan and publish the image to GHCR by digest on merge to main

## Why

Add .github/workflows/images.yml following the github-argocd-continuous-deployment reference pattern: build with buildx, a non-root check, a vulnerability scan with a fail threshold on CRITICAL, an artifact secret scan with a planted-secret negative control that must fail, refuse to push if the SHA tag already exists, push ghcr.io/gqadonis/sellbird:<sha>, and expose the digest as a job output. This change serves phase goal G3 of KBD phase `postgres-gke-deployment`.

## What Changes

Add .github/workflows/images.yml following the github-argocd-continuous-deployment reference pattern: build with buildx, a non-root check, a vulnerability scan with a fail threshold on CRITICAL, an artifact secret scan with a planted-secret negative control that must fail, refuse to push if the SHA tag already exists, push ghcr.io/gqadonis/sellbird:<sha>, and expose the digest as a job output. paths-ignore the overlay so the bot's pin commit does not rebuild.

## Capabilities

- **New Capabilities**: `image-build` — Builds, scans and publishes the Sellbird image by digest.
- **Modified Capabilities**: none

## Impact

- Scope: ci
- Depends on: baseline-test-green, cluster-ready-container-image
- Owner role: `platform-engineer`
- Plan: `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md` (change 8)
