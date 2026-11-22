## Why

Three small defects carried from the last phase: any http JWKS address is accepted, exists() says one thing and does another for a missing database, and the local stand-in's flint-gate port is fixed.

## What Changes

- Require https for the JWKS address unless the host is loopback or ends in .svc or .svc.cluster.local; add tests for each accepted and refused form.
- Make exists() return False only for sqlstate 3D000 or 42P01, raise for any other sqlstate and for any connect failure without a sqlstate, with a test for each case, correct the docstring and comment, and add a connect-time missing-database test.
- Make the local stand-in's flint-gate host port a variable `SELLBIRD_LOCAL_GATE_PORT` defaulting to 4456.

## Impact

- Affected capability: `hosted-fixes`
- Files: infra/local/compose.yaml, scripts/local/**; sellbird/auth/config.py, tests/test_gateway_config*.py; sellbird/storage_postgres/__init__.py, tests/storage_contract/test_pg_failures.py
- Phase: `sellbird-go-live`; verified once at the phase boundary, not per task.
