# Tasks

Model routes for these tasks: see **TASK MODEL ASSIGNMENTS** in `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md`, rows for change `postgres-storage-backend`.

## 3. Add a Postgres 18 storage backend beside SQLite with reversible migrations

- [ ] 3.1 Define the backend-neutral connection and error contract in sellbird/storage.py (verify at the phase boundary per the plan's coverage table)
- [ ] 3.2 Implement the psycopg 3 async Postgres backend and dialect layer (verify at the phase boundary per the plan's coverage table)
- [ ] 3.3 Author versioned up/down Postgres migrations, schema_version table and least-privilege roles (verify at the phase boundary per the plan's coverage table)
- [ ] 3.4 Port signal-code governance and the outbox claim to concurrency-safe Postgres forms (verify at the phase boundary per the plan's coverage table)
- [ ] 3.5 Route dashboard.py's raw sqlite3 read and inline feedback DDL through the storage seam (verify at the phase boundary per the plan's coverage table)
- [ ] 3.6 Run the storage contract tests against SQLite and a Postgres 18 container, including migration up/down/up and app-role DDL refusal (verify at the phase boundary per the plan's coverage table)
- [ ] 3.7 Add `sellbird storage migrate` using a migration-role DSN, separate from the app-role DSN used at runtime (verify at the phase boundary per the plan's coverage table)
- [ ] 3.8 Author hand-written expected-result fixtures for cohorts and sending safety (quiet hours, daily limit, opt-out/suppression, approval ladder) independent of either backend (verify at the phase boundary per the plan's coverage table)
