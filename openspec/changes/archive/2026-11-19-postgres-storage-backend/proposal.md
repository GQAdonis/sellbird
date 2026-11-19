# Add a Postgres 18 storage backend beside SQLite with reversible migrations

## Why

Register a psycopg 3 async backend behind sellbird/storage.py with a small dialect layer (placeholders, INSERT OR IGNORE/REPLACE, datetime/julianday, json_extract), versioned up/down migrations under migrations/postgres with a schema_version table, a foreign key from observations.signal_code to signal_codes, an outbox claim that is exactly-once under concurrent writers (UPDATE ... This change serves phase goal G2 of KBD phase `postgres-gke-deployment`.

## What Changes

Register a psycopg 3 async backend behind sellbird/storage.py with a small dialect layer (placeholders, INSERT OR IGNORE/REPLACE, datetime/julianday, json_extract), versioned up/down migrations under migrations/postgres with a schema_version table, a foreign key from observations.signal_code to signal_codes, an outbox claim that is exactly-once under concurrent writers (UPDATE ... WHERE status RETURNING / SKIP LOCKED), a backend-neutral IntegrityError, and the dashboard's raw sqlite3 read and inline DDL routed through the seam. The app role has no DDL rights at runtime. SQLite behaviour is unchanged. Contract tests run against both backends, Postgres via a real flint-forge PG18 container.

## Capabilities

- **New Capabilities**: `storage-backends` — Lets Sellbird keep its state in SQLite for local installs or in Postgres 18 for hosted deployments with identical behaviour.
- **Modified Capabilities**: none

## Impact

- Scope: db | storage | tests
- Depends on: platform-interface-contract
- Owner role: `database-engineer`
- Plan: `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md` (change 3)
