## Why

The hosted pod only serves the dashboard. The heartbeat refuses to start without a .env file, the dashboard cannot see a heartbeat in another container, and provider secrets have no way in.

## What Changes

- In gateway mode make the setup check ignore the missing .env file and judge the trained configuration only, and make every cycle, including an idle one, write its action-log row; local mode unchanged; tests for both.
- In gateway mode report the heartbeat as running only when its newest row in the action log is younger than three heartbeat intervals; tests on both backends.
- In gateway mode hide the start and stop controls and show the last cycle time.
- Confirm whether any dashboard action sends mail or calls a provider directly and record the per-container secret split in the change design.
- Add a `heartbeat` container running `sellbird run` to the Deployment, sharing /data, with optional secretKeyRef entries per the recorded split, resource limits and the same security context.

## Impact

- Affected capability: `hosted-operation`
- Files: infra/k8s/base/deployment.yaml; openspec/changes/hosted-heartbeat/design.md; sellbird/dashboard.py, sellbird/state.py, tests/** (not sellbird/main.py); sellbird/main.py, tests/test_main*.py; sellbird/web/**
- Phase: `sellbird-go-live`; verified once at the phase boundary, not per task.
