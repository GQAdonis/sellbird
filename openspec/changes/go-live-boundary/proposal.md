## Why

The last phase lost five boundary attempts to its own harness. The scenario scripts are written and reviewed as a change of their own, with every oracle readable before the run.

## What Changes

- Write scripts/boundary/golive/preflight.sh: tools, free ports, kube context, gh auth, clean evidence folder; the static and local scenario scripts with their negative controls; and the workflow graph check.
- Write the live scenario scripts (rollout, heartbeat cycle, restart survival, no-send) that read counts and timestamps only and never print a secret, name or address.

## Impact

- Affected capability: `golive-verification`
- Files: scripts/boundary/golive/**
- Phase: `sellbird-go-live`; verified once at the phase boundary, not per task.
