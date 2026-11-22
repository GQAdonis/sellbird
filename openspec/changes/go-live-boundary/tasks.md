## 1. Boundary scripts for the go-live scenarios

- [x] 1.1 Write scripts/boundary/golive/preflight.sh: tools, free ports, kube context, gh auth, clean evidence folder; the static and local scenario scripts with their negative controls; and the workflow graph check (role: qa-engineer)
- [x] 1.2 Write the live scenario scripts (rollout, heartbeat cycle, restart survival, no-send) that read counts and timestamps only and never print a secret, name or address (role: qa-engineer)
