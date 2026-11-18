# Tasks

Model routes for these tasks: see **TASK MODEL ASSIGNMENTS** in `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md`, rows for change `sqlite-to-postgres-move-tool`.

## 5. A tested tool that moves a sellbird.db into the Postgres backend

- [ ] 5.1 Implement the move command with dependency-ordered transactional copy and non-empty-target refusal (verify at the phase boundary per the plan's coverage table)
- [ ] 5.2 Build a fictional fixture sellbird.db and tests comparing row counts and invariants after the move (verify at the phase boundary per the plan's coverage table)
