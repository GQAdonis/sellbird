# Tasks

Model routes for these tasks: see **TASK MODEL ASSIGNMENTS** in `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md`, rows for change `baseline-test-green`.

## 1. Make the configured test command runnable and the baseline suite green

- [ ] 1.1 Make the project test command runnable in .venv via uv-managed dev extras (verify at the phase boundary per the plan's coverage table)
- [ ] 1.2 Make test_a_long_french_reply_is_quick and test_nested_testimonials_are_bounded deterministic while still failing on super-linear processing (verify at the phase boundary per the plan's coverage table)
- [ ] 1.3 Record the baseline decision for uv.lock and the test command in project.json notes and the change design (verify at the phase boundary per the plan's coverage table)
- [ ] 1.4 Write scripts/boundary/preflight.sh that runs pinned, containerized actionlint, kustomize, yq and the Postgres 18 client so the boundary needs no host installs (verify at the phase boundary per the plan's coverage table)
