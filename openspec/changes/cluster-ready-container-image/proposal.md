# Make the Sellbird image reproducible and runnable in Kubernetes

## Why

Pin the Claude CLI to an exact version with checksum verification instead of an unpinned install script, move writable state to a /data volume so the root filesystem can be read-only, run gateway mode by configuration with a health endpoint reachable from the Service, keep the non-root user, include the Postgres client dependencies, and never log the token. This change serves phase goal G3 of KBD phase `postgres-gke-deployment`.

## What Changes

Pin the Claude CLI to an exact version with checksum verification instead of an unpinned install script, move writable state to a /data volume so the root filesystem can be read-only, run gateway mode by configuration with a health endpoint reachable from the Service, keep the non-root user, include the Postgres client dependencies, and never log the token. The brain reads CLAUDE_CODE_OAUTH_TOKEN from the environment only (Secret `sellbird-claude`), with no credential written under /data or /home.

## Capabilities

- **New Capabilities**: `container-runtime` — Defines how the Sellbird container behaves when run in Kubernetes.
- **Modified Capabilities**: none

## Impact

- Scope: container
- Depends on: postgres-storage-backend, hosted-gateway-mode
- Owner role: `platform-engineer`
- Plan: `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md` (change 6)
