# A tested tool that moves a sellbird.db into the Postgres backend

## Why

Add `sellbird storage move --from <sqlite> --to <postgres-dsn>` that copies every table in dependency order inside one transaction, preserves ids, timestamps, JSON and signal confirmation state, refuses a non-empty target, and reports per-table row counts. This change serves phase goal G2 of KBD phase `postgres-gke-deployment`.

## What Changes

Add `sellbird storage move --from <sqlite> --to <postgres-dsn>` that copies every table in dependency order inside one transaction, preserves ids, timestamps, JSON and signal confirmation state, refuses a non-empty target, and reports per-table row counts. Exercised only with fixture databases; moving the operator's real data is excluded.

## Capabilities

- **New Capabilities**: `storage-move` — Moves an existing SQLite Sellbird database into an empty Postgres backend without losing data.
- **Modified Capabilities**: none

## Impact

- Scope: cli | db
- Depends on: postgres-storage-backend
- Owner role: `database-engineer`
- Plan: `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md` (change 5)
