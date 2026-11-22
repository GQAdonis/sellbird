## Why

The platform interface changes (a volume, a second container, new optional secrets), operators need a hosted runbook, and two fixes belong to the platform.

## What Changes

- Update docs/platform-interface.md to version 3: the volume claim, Recreate strategy, heartbeat container, optional provider secrets, migration ServiceAccount and DNS rule.
- Write docs/hosted-operations.md: training with kubectl exec, loading provider secrets, approval and pause controls, reading heartbeat status.
- Add CHANGELOG entries for every change in this phase, including the stricter exists() and value-free error text from the last phase.
- Draft the platform request: strip the Cookie header upstream (SEC-02), narrow the deploy App's push scope and remove its rule bypass (SEC-03), and point the overlay at the new base.

## Impact

- Affected capability: `hosted-docs`
- Files: .agent-team/work/platform-request-go-live.md; CHANGELOG.md; docs/hosted-operations.md, README.md; docs/platform-interface.md
- Phase: `sellbird-go-live`; verified once at the phase boundary, not per task.
