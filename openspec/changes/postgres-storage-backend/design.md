# Design: Add a Postgres 18 storage backend beside SQLite with reversible migrations

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 3). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Register a psycopg 3 async backend behind sellbird/storage.py with a small dialect layer (placeholders, INSERT OR IGNORE/REPLACE, datetime/julianday, json_extract), versioned up/down migrations under migrations/postgres with a schema_version table, a foreign key from observations.signal_code to signal_codes, an outbox claim that is exactly-once under concurrent writers (UPDATE ... WHERE status RETURNING / SKIP LOCKED), a backend-neutral IntegrityError, and the dashboard's raw sqlite3 read and inline DDL routed through the seam. The app role has no DDL rights at runtime. SQLite behaviour is unchanged. Contract tests run against both backends, Postgres via a real flint-forge PG18 container.

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

Changed baseline test files (justified): none yet.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.

## Open Questions

None that change what gets built; the platform contract's operator agreement is tracked as a boundary receipt.
