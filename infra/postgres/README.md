# Postgres for Sellbird

Sellbird keeps its state in SQLite by default. A hosted install can keep it in
Postgres 18 (the flint-forge image) instead: set `SELLBIRD_DATABASE_URL` to a
`postgresql://` connection string for the runtime role and install the extra
(`pip install 'sellbird[postgres]'`).

| File | What it is |
|---|---|
| `provision.sql` | The database and its two roles, exactly as `docs/platform-interface.md` provisions them. The platform runs this in the shared cluster; use it for a local or test server. |
| `../../migrations/postgres/` | The schema: numbered, reversible migrations (`NNNN_name.up.sql` / `.down.sql`). |

## Roles

- `sellbird_migrate` owns the schema. Only it runs `sellbird storage migrate`.
- `sellbird_app` is what Sellbird runs as. It reads and writes rows; it cannot
  create, alter, drop or truncate anything, and Sellbird refuses to start when
  the schema version isn't the one its code expects.

## Commands

```bash
# Apply pending migrations (migration role). Reads SELLBIRD_MIGRATE_DATABASE_URL,
# else SELLBIRD_DATABASE_URL (the migration Job gets the migrate role's string there).
sellbird storage migrate
sellbird storage status
# Operator-only rollback to a version (never automatic):
sellbird storage down --to 4 --yes
```

## Running the storage tests against Postgres

The contract tests run on SQLite always, and on Postgres when both of these
point at a throwaway database provisioned with `provision.sql` (the tests drop
and recreate Sellbird's schema there):

```bash
export SELLBIRD_TEST_PG_MIGRATE_DSN=postgresql://sellbird_migrate:...@127.0.0.1:5432/sellbird
export SELLBIRD_TEST_PG_APP_DSN=postgresql://sellbird_app:...@127.0.0.1:5432/sellbird
pytest tests/storage_contract tests/test_outbox_concurrency.py tests/test_send_safety_parity.py
```

The migration test compares `pg_dump --schema-only` before and after a full
down and up, so `pg_dump` 18 must be on `PATH` (or named by
`SELLBIRD_TEST_PG_DUMP`). With the DSNs unset the Postgres cases skip and say why.
