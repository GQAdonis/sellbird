# Design: Add a Postgres 18 storage backend beside SQLite with reversible migrations

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 3). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Register a psycopg 3 async backend behind sellbird/storage.py with a small dialect layer (placeholders, INSERT OR IGNORE/REPLACE, datetime/julianday, json_extract), versioned up/down migrations under migrations/postgres with a schema_version table, a foreign key from observations.signal_code to signal_codes, an outbox claim that is exactly-once under concurrent writers (UPDATE ... WHERE status RETURNING / SKIP LOCKED), a backend-neutral IntegrityError, and the dashboard's raw sqlite3 read and inline DDL routed through the seam. The app role has no DDL rights at runtime. SQLite behaviour is unchanged. Contract tests run against both backends, Postgres via a real flint-forge PG18 container.

### How it is built

- **Selection.** A `postgresql://` (or `postgres://`) connection string is itself a storage locator. `sellbird.storage` registers the built-in backend (`sellbird.storage_postgres`) lazily on first use, so a SQLite install never imports psycopg. `StateManager()` uses `SELLBIRD_DATABASE_URL` when set, else `data/sellbird.db`; SQLite stays the default.
- **One code path.** The stores keep writing SQLite-dialect SQL with `?` placeholders. The backend returns an aiosqlite-shaped connection (`sellbird/storage_postgres/connection.py`) that rewrites each statement (`dialect.py`) and keeps sqlite3's transaction rules: reads autocommit; the first write opens a READ COMMITTED transaction that lasts until commit/rollback; explicit `BEGIN` opens REPEATABLE READ (a deferred SQLite snapshot); a failed statement inside a transaction is undone by a savepoint and leaves the rest usable; closing without commit discards.
- **Error contract.** `storage.DatabaseError`, `IntegrityError`, `OperationalError`, `PermissionDenied` and `SchemaVersionError` each subclass the matching sqlite3 class, so existing `except sqlite3.IntegrityError` handlers catch both backends. Postgres messages are rewritten to SQLite's shape ("UNIQUE constraint failed: mailboxes.address", "unknown signal_code: not in signal_codes vocabulary") and never carry the offending values or the DSN; errors are raised `from None` with `.sqlstate` kept.
- **Schema parity.** Text columns are `COLLATE "C"` (byte order, as SQLite's BINARY), timestamps stay ISO-8601 text with the same defaults, INTEGER is bigint and REAL double precision. Each table ends with a hidden `rowid` identity (results omit it unless the outer select list names it) so `ORDER BY ..., rowid` tie-breaks keep working. No foreign keys besides the governed vocabulary, because SQLite never enforced them and several id columns default to `''`.
- **Values.** numeric loads as int (or float with a fraction) so `SUM` over integers is an int as in SQLite; booleans load as 1/0; bool parameters dump as 1/0; datetime/date parameters dump as sqlite3's default adapters store them.
- **RLS.** Not enabled: single tenant, one workspace per database isolated by database and role (ADR 0001, platform contract).

### SQLite-only constructs and their Postgres form

| SQLite | Postgres | Where |
|---|---|---|
| `?` placeholders | `%s`, literal `%` doubled | dialect |
| `INSERT OR IGNORE INTO` (7 uses) | `INSERT INTO ... ON CONFLICT DO NOTHING` (all unique indexes, partial ones included, are arbiters) | dialect |
| `INSERT OR REPLACE INTO settings` (state.py stop_company) | `ON CONFLICT (pk) DO UPDATE SET` each listed non-key column (primary keys from a registry of every table) | dialect |
| `x IS NOT 'v'` | `IS DISTINCT FROM` | dialect |
| scalar `MAX(a, b)` (save_email_pattern) | `GREATEST(a, b)` (and `MIN` to `LEAST`) | dialect |
| `CURRENT_TIMESTAMP`, `datetime('now')`, `datetime(x, '-N days')`, `date(...)`, `julianday(...)` | `sb_now()`, `sb_datetime`, `sb_date`, `sb_julianday`: SQL functions in migration 0001 returning SQLite's exact text | dialect + migration 0001 |
| `json_extract`, `json_valid` | `sb_json_extract` (jsonb `#>` on a parsed SQLite path, typed like SQLite: strings unquoted, booleans 1/0, NULL on malformed JSON), `sb_json_valid` (`IS JSON`) | dialect + migration 0001 |
| `instr`, `ifnull`, `CAST(... AS REAL)` | `strpos`, `coalesce`, `double precision` | dialect |
| `LIKE` (ASCII case-insensitive) | `ILIKE` on C-collated text (only ASCII folds) | dialect |
| NULLs sort first ascending | `NULLS FIRST` / `NULLS LAST` appended to each ORDER BY item | dialect |
| `rowid` | hidden identity column per table | migrations + connection |
| `executescript` | commit, then one multi-statement execute | connection |
| `PRAGMA journal_mode/synchronous/foreign_keys/busy_timeout`, `PRAGMA user_version` | no-ops; user_version reads `schema_version` | connection |
| bare columns with `GROUP BY` (get_observations latest_only) | `DISTINCT ON (company_id, signal_code) ... ORDER BY observed_at DESC, rowid DESC` | state.py, Postgres branch only |
| `GROUP BY p.signal_code` selecting `sc.label`, `sc.status` (signal_counts) | group by all three (same result in SQLite) | state.py |
| `ON CONFLICT(date) DO UPDATE SET c = c + 1` | `c = usage_log.c + 1` (valid in both) | state.py |
| governance trigger `trg_observations_signal_known` | foreign key `observations_signal_code_fkey` (ON DELETE/UPDATE RESTRICT) | migration 0003 |
| inline `CREATE TABLE IF NOT EXISTS feedback` in dashboard.py | migration 0005 (SQLite already creates it in its migration 1); dashboard calls `StateManager.add_feedback` | dashboard.py, migrations |
| raw `sqlite3.connect(... mode=ro)` in dashboard.py | `storage.read_one(locator, sql)` (SQLite: read-only file URI; Postgres: short-lived sync connection) | dashboard.py, storage.py |

Unsupported constructs (`INSERT OR ABORT/FAIL/ROLLBACK`, `GLOB`, numbered or named parameters, multiple statements with parameters) raise `DialectError` before anything runs.

### Exactly-once outbox claim

`claim_outbox_item` is unchanged: one `UPDATE outbox SET status = 'sending' ... WHERE id = ? AND status = 'approved' AND (send_at IS NULL OR send_at <= ?)` committed on its own, success when the row count is 1. On Postgres under READ COMMITTED the first claimer row-locks the item; every concurrent claimer blocks on that lock, and when the first commits Postgres re-evaluates the WHERE clause against the new row version (status is now 'sending'), so it updates nothing and its row count is 0. Exactly one claimer sees 1, whether claimers are coroutines, threads or processes. SQLite serialises writers, as before. The stale sweep (`datetime(updated_at) < datetime(?)`) runs through `sb_datetime` and fails abandoned claims identically.

### Migrations and roles

- `migrations/postgres/NNNN_name.up.sql` / `.down.sql`: 0001 SQLite-compatible functions, 0002 core tables, 0003 signals and observations, 0004 outbox, suppressions and mailboxes, 0005 feedback. `EXPECTED_SCHEMA_VERSION = 5` in `sellbird/storage_postgres/__init__.py`; a test keeps it equal to the newest file.
- The runner (`sellbird/storage_postgres/migrate.py`) creates `schema_version (version, name, checksum, applied_at)`, revokes write privileges on it from every other role (the runtime role keeps SELECT), takes a session advisory lock, applies each migration and its version row in one transaction, refuses a role without CREATE on `public`, and stops when an applied migration's file has changed or is unknown.
- `sellbird storage migrate [--to N]`, `sellbird storage status`, `sellbird storage down --to N --yes` (operator only). The DSN comes from `SELLBIRD_MIGRATE_DATABASE_URL`, else `SELLBIRD_DATABASE_URL` (the migration Job receives the migration role's string under that key per the platform contract), or `--dsn-env`. It is never printed.
- The app runs as `sellbird_app`; `StateManager.init_db` on Postgres only calls `check_schema`, which fails closed unless `MAX(version)` equals `EXPECTED_SCHEMA_VERSION`.
- `infra/postgres/provision.sql` reproduces the platform contract's roles, database, grants and role settings for local and test servers. Migrations create no roles, extensions, grants or policies.

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

New test files (none of them baseline):

- `tests/storage_contract/test_dialect.py`: the rewrite, statement by statement (no database).
- `tests/storage_contract/test_contract.py`: state operations on both backends, including governance, claim, stale sweep, NULL ordering, opt-out, suppression, company stop, settings, usage sums as ints, patterns, feedback, mailbox duplicate message, transaction semantics and `read_one`.
- `tests/storage_contract/test_cohorts.py` with `fixtures/cohorts.json`, and `tests/test_send_safety_parity.py` with `fixtures/sending_safety.json`: hand-authored expectations (quiet hours, daily limit, opt-out, address and domain suppression, approval ladder, not-yet-due), the Sender draining into the recording `FakeProvider` from `tests/test_outbox_native.py`.
- `tests/storage_contract/test_migrations.py`: file pairing and content rules; up, down, up compared with `pg_dump --schema-only` and a catalog fingerprint; each migration reversed on its own; schema_version equals the newest; the runtime role refused CREATE TABLE, ALTER TABLE, DROP, TRUNCATE, CREATE FUNCTION and writing schema_version; migrating as the runtime role refused; the app refusing a behind or missing schema; an edited applied migration stopping the run.
- `tests/test_outbox_concurrency.py`: 8 claimers (coroutines, then threads with their own event loops) on one approved item, 50 rounds, exactly one claim each round.

Postgres cases need `SELLBIRD_TEST_PG_MIGRATE_DSN` and `SELLBIRD_TEST_PG_APP_DSN` for a throwaway database provisioned with `infra/postgres/provision.sql`, plus `pg_dump` 18 on PATH (or `SELLBIRD_TEST_PG_DUMP`) and `pip install -e '.[postgres,dev]'`. Unset, they skip with that reason; set, a missing pg_dump or psycopg fails rather than skips.

Changed baseline test files (justified): none.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.
- Hosted dashboard still on SQLite: `sellbird/dashboard.py` opens `str(DB_PATH)` directly in several places outside this change's two spots (`query_db`, `_state`, page handlers, `inbox_routes.MailboxStore`). With `SELLBIRD_DATABASE_URL` set, the heartbeat, CLI and every bare `StateManager()` use Postgres but the dashboard does not until its owner replaces `str(DB_PATH)` with `state.database_locator()` and `DB_PATH.exists()` with `storage.exists(...)`. Requested from the dashboard owner.
- Image contents: the Dockerfile copies `sellbird/` only; the migration Job needs `migrations/` (`COPY migrations/ migrations/`, or `SELLBIRD_MIGRATIONS_DIR`) and the image needs `psycopg[binary]`. Requested from the platform engineer.
- Test isolation: `tests/conftest.py` pops `SELLBIRD_HOME` but not `SELLBIRD_DATABASE_URL`; a developer with it exported would point bare `StateManager()` tests at Postgres. Requested from QA (baseline file, not changed here).
- Connections: one connection per operation, as with SQLite, with no pool; concurrent dashboard requests count against the runtime role's limit of 20. Lock waits are bounded by the role's 30 s statement timeout rather than SQLite's busy timeout. A pool is a follow-up if the boundary measures a need.
- Known dialect differences, none used by Sellbird today: SQLite `OR IGNORE` also ignores NOT NULL/CHECK failures; `OR REPLACE` there resolves any unique conflict, here only the primary key; `LIKE` patterns treat backslash as an escape on Postgres; Julian-day input, `localtime` and month-end arithmetic in the date functions; a text column compared with an integer parameter errors on Postgres.

## Open Questions

None that change what gets built; the platform contract's operator agreement is tracked as a boundary receipt. The move of an existing `data/sellbird.db` into Postgres is the separate change `sqlite-to-postgres-move-tool`; the hidden `rowid` columns use `GENERATED BY DEFAULT` so that tool can carry SQLite's rowids across and keep insertion order.
