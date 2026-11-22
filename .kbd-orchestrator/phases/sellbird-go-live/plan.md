# Plan — sellbird-go-live

Written 2026-11-22. Status: **adopted by the operator on 2026-11-22** (decision `contract-adoption-sellbird-go-live-c47f7a03`, digest `c47f7a03…`). Nothing is built or committed.

## Inputs, decisions and recalled lessons

- Inputs: `assessment.md`, `analysis.md`, `library-candidates.json` (one adoption: `uv`, for the lock file).
- Operator decisions (2026-11-22): go-live means **Operating**; SEC-03, SEC-04 and SEC-05 are all in scope.
- Lessons that shaped this plan:
  - "Boundary gates must launch the packaged artifact": the live scenarios run against the published image in the cluster.
  - "External integrations require at least one real-service test": the pipeline controls run on the real repository, not a scratch copy.
  - "Ask once at phase boundary for operator-only actions": all six operator steps are listed together below.
  - From the last reflection (9 boundary attempts, 7 amendments): the boundary scripts are a change of their own (`go-live-boundary`), written and reviewed before the run, with a preflight that checks tools, ports and logins. The repair budget is 3.
- Confirmed from the analysis review: the heartbeat writes one row per cycle to the `actions` table through `State.log_action` (`sellbird/state.py` line 2582, called from `sellbird/main.py` line 470 with `agent="main"`), on both backends. `hosted-heartbeat/2` reads that table.
- Still to confirm, by `hosted-heartbeat/4` before `hosted-heartbeat/5` is written: whether any dashboard action needs a mailbox or provider key. Its answer is read at the cumulative review.
- File locations confirmed in this checkout on 2026-11-22: `.github/workflows/tests.yml` and `.github/workflows/images.yml` exist (the review packet's file tree omits dot directories); `infra/github/` holds only the ruleset documentation.

## Security findings → where they are closed

| Finding | Closed by | Scenario |
|---|---|---|
| SEC-03, deploys not gated on tests | `pipeline-hardening/1` | SCN-PIPE-001 |
| SEC-03, persisted credentials | Already `persist-credentials: false` on both checkouts; `pipeline-hardening/1` re-checks every checkout it touches | cumulative review |
| SEC-03, deploy App push scope and rule bypass | **Not closed here.** Requested from the platform in `go-live-docs/4`; a platform-repo change | none |
| SEC-04, image ID after scans; Trivy unchecked | `pipeline-hardening/2`, `/3`, `/4` | SCN-PIPE-002 |
| SEC-05, no hash lock | `pipeline-hardening/5` | SCN-LOCK-001 |
| SEC-02, cookie forwarded upstream | **Not closed here.** Platform request in `go-live-docs/4` | none |
| F1, `exists()` contract for a missing database | `hosted-small-fixes/2` | SCN-REG-001 |
| F2, missing CHANGELOG entry | `go-live-docs/3` | cumulative review |
| F3, fixed flint-gate port in the local stand-in | `hosted-small-fixes/3` | used by `preflight.sh` and `standin-up.sh`; cumulative review |

## Goals proposed for adoption

1. The hosted Sellbird runs its outreach loop in the cluster and restarts on its own.
2. Training and settings survive restarts and deploys.
3. No email is sent without approval.
4. A red test run or a failing scan cannot ship, and the image installs only hash-locked dependencies.
5. A fresh install does not deadlock; the JWKS, exists() and DNS defects are closed.
6. Local single-user mode is unchanged.

## Method note: when things are verified

VLBV. All 22 tasks are written first, with no tests, builds or checks run in between. The boundary packet below then runs once. A failure goes to an operator-authorized repair that reruns only the affected scenarios.

## CHANGE LIST (ordered)

### 1. `hosted-persistent-home` — Keep the hosted home folder and fix fresh installs

The hosted pod's home folder is temporary storage, so training and settings vanish on every restart; a fresh install deadlocks on the migration Job's service account; DNS breaks under NodeLocal DNSCache.

- `hosted-persistent-home/1` Replace the /data emptyDir with a 1Gi ReadWriteOnce PersistentVolumeClaim `sellbird-data` and set the Deployment strategy to Recreate. Role: platform-engineer. Files: infra/k8s/base/**.
- `hosted-persistent-home/2` Give the migration Job its own ServiceAccount `sellbird-migrate`, itself a PreSync hook at an earlier wave than the Job. Role: platform-engineer. Files: infra/k8s/base/**.
- `hosted-persistent-home/3` Add a DNS egress rule for UDP and TCP 53 to 169.254.20.10/32 beside the kube-dns rule; keep the metadata server blocked. Role: platform-engineer. Files: infra/k8s/base/networkpolicy.yaml.

### 2. `hosted-small-fixes` — JWKS address rule, exists() contract and local port

Three small defects carried from the last phase: any http JWKS address is accepted, exists() says one thing and does another for a missing database, and the local stand-in's flint-gate port is fixed.

- `hosted-small-fixes/1` Require https for the JWKS address unless the host is loopback or ends in .svc or .svc.cluster.local; add tests for each accepted and refused form. Role: identity-engineer. Files: sellbird/auth/config.py, tests/test_gateway_config*.py.
- `hosted-small-fixes/2` Make exists() return False only for sqlstate 3D000 or 42P01, raise for any other sqlstate and for any connect failure without a sqlstate, with a test for each case, correct the docstring and comment, and add a connect-time missing-database test. Role: database-engineer. Files: sellbird/storage_postgres/__init__.py, tests/storage_contract/test_pg_failures.py.
- `hosted-small-fixes/3` Make the local stand-in's flint-gate host port a variable `SELLBIRD_LOCAL_GATE_PORT` defaulting to 4456. Role: platform-engineer. Files: infra/local/compose.yaml, scripts/local/**.

### 3. `pipeline-hardening` — Gate deploys on tests, trust the scanned image, lock dependencies

A red test run does not stop a deploy; the image ID that publish trusts is read after third-party scans ran; the Trivy binary is unchecked; dependencies install from ranges without hashes; no failing scan has ever been shown to stop a release.

library: cand-001 (uv, for the lock file only).

- `pipeline-hardening/1` Make tests.yml callable (`workflow_call`), call it from images.yml and make the deploy job need it. Role: platform-engineer. Files: .github/workflows/**.
- `pipeline-hardening/2` Record the image ID and save the image tar immediately after the build step; after all scans recompute the ID and fail on mismatch; publish from the saved tar. Role: platform-engineer. Files: .github/workflows/images.yml.
- `pipeline-hardening/3` Pin a SHA-256 for the Trivy binary in the workflow and verify it before any scan. Role: platform-engineer. Files: .github/workflows/images.yml, scripts/ci/**.
- `pipeline-hardening/4` Add workflow_dispatch control inputs `failing-test` and `vulnerable-image` that run the real gates and can never publish or deploy. Role: platform-engineer. Files: .github/workflows/**, scripts/ci/**.
- `pipeline-hardening/5` Generate a tracked requirements.lock with hashes for linux amd64 and arm64 using uv; install it with --require-hashes in the Dockerfile; fail CI when the lock is stale. Role: platform-engineer. Files: Dockerfile, requirements.lock, .github/workflows/**, scripts/ci/**.

### 4. `hosted-heartbeat` — Run the outreach loop in the cluster

The hosted pod only serves the dashboard. The heartbeat refuses to start without a .env file, the dashboard cannot see a heartbeat in another container, and provider secrets have no way in.

- `hosted-heartbeat/1` In gateway mode make the setup check ignore the missing .env file and judge the trained configuration only, and make every cycle, including an idle one, write its action-log row; local mode unchanged; tests for both. Role: backend-engineer. Files: sellbird/main.py, tests/test_main*.py.
- `hosted-heartbeat/2` In gateway mode report the heartbeat as running only when its newest row in the action log is younger than three heartbeat intervals; tests on both backends. Role: backend-engineer. Files: sellbird/dashboard.py, sellbird/state.py, tests/** (not sellbird/main.py).
- `hosted-heartbeat/3` In gateway mode hide the start and stop controls and show the last cycle time. Role: frontend-engineer. Files: sellbird/web/**.
- `hosted-heartbeat/4` Confirm whether any dashboard action sends mail or calls a provider directly and record the per-container secret split in the change design. Role: backend-engineer. Files: openspec/changes/hosted-heartbeat/design.md.
- `hosted-heartbeat/5` Add a `heartbeat` container running `sellbird run` to the Deployment, sharing /data, with optional secretKeyRef entries per the recorded split, resource limits and the same security context. Role: platform-engineer. Files: infra/k8s/base/deployment.yaml.

### 5. `go-live-docs` — Document hosted operation and file platform requests

The platform interface changes (a volume, a second container, new optional secrets), operators need a hosted runbook, and two fixes belong to the platform.

- `go-live-docs/1` Update docs/platform-interface.md to version 3: the volume claim, Recreate strategy, heartbeat container, optional provider secrets, migration ServiceAccount and DNS rule. Role: documentation-specialist. Files: docs/platform-interface.md.
- `go-live-docs/2` Write docs/hosted-operations.md: training with kubectl exec, loading provider secrets, approval and pause controls, reading heartbeat status. Role: documentation-specialist. Files: docs/hosted-operations.md, README.md.
- `go-live-docs/3` Add CHANGELOG entries for every change in this phase, including the stricter exists() and value-free error text from the last phase. Role: documentation-specialist. Files: CHANGELOG.md.
- `go-live-docs/4` Draft the platform request: strip the Cookie header upstream (SEC-02), narrow the deploy App's push scope and remove its rule bypass (SEC-03), and point the overlay at the new base. Role: documentation-specialist. Files: .agent-team/work/platform-request-go-live.md.

### 6. `go-live-boundary` — Boundary scripts for the go-live scenarios

The last phase lost five boundary attempts to its own harness. The scenario scripts are written and reviewed as a change of their own, with every oracle readable before the run.

- `go-live-boundary/1` Write scripts/boundary/golive/preflight.sh: tools, free ports, kube context, gh auth, clean evidence folder; the static and local scenario scripts with their negative controls; and the workflow graph check. Role: qa-engineer. Files: scripts/boundary/golive/**.
- `go-live-boundary/2` Write the live scenario scripts (rollout, heartbeat cycle, restart survival, no-send) that read counts and timestamps only and never print a secret, name or address. Role: qa-engineer. Files: scripts/boundary/golive/**.

Total: 6 changes, 22 tasks.

## EXECUTION ROUND ORDER

| Round | Changes | Why this order |
|---|---|---|
| 1 | `hosted-persistent-home`, `hosted-small-fixes`, `pipeline-hardening` | Disjoint files: infra/k8s/base, sellbird/auth + storage + infra/local, and .github + Dockerfile. |
| 2 | `hosted-heartbeat` | Edits infra/k8s/base/deployment.yaml after round 1 and sellbird/main.py, dashboard.py, web. |
| 3 | `go-live-docs`, `go-live-boundary` | Describe and verify what rounds 1 and 2 built. |

Two writers never share a file inside a round. Reviewer and security-reviewer roles stay dormant until all three rounds are complete.

## TASK MODEL ASSIGNMENTS

Discovery (2026-11-22): active harness Claude Code; project subagents for every role below are installed and listed by the harness. Per-agent reasoning effort is not set here: the operator has not asked for one. Native alternative: Codex CLI, not planned.

| Phase path | Change ID | Backend task ID | Requirements | Provider/model | Reasoning effort | Rationale | Harness and route | Availability |
|---|---|---|---|---|---|---|---|---|
| sellbird-go-live | hosted-persistent-home | 1 (label 1.1) | medium reasoning; Kubernetes storage and rollout semantics | anthropic/claude-opus-5-5 | default | Role `platform-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `platform-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | hosted-persistent-home | 2 (label 1.2) | medium reasoning; Argo CD hook ordering | anthropic/claude-opus-5-5 | default | Role `platform-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `platform-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | hosted-persistent-home | 3 (label 1.3) | low reasoning; NetworkPolicy | anthropic/claude-opus-5-5 | default | Role `platform-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `platform-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | hosted-small-fixes | 1 (label 1.1) | medium reasoning; trust boundary; URL parsing edge cases | anthropic/claude-opus-5-5 | default | Role `identity-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `identity-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | hosted-small-fixes | 2 (label 1.2) | medium reasoning; psycopg error shapes | anthropic/claude-opus-5-5 | default | Role `database-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `database-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | hosted-small-fixes | 3 (label 1.3) | low reasoning; compose file | anthropic/claude-sonnet-5-5 | default | Role `platform-engineer` owns these files; sonnet-class is enough for bounded docs, UI or config | Claude Code subagent `platform-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | pipeline-hardening | 1 (label 1.1) | medium reasoning; GitHub Actions reusable workflows | anthropic/claude-opus-5-5 | default | Role `platform-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `platform-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | pipeline-hardening | 2 (label 1.2) | high reasoning; supply-chain ordering | anthropic/claude-opus-5-5 | default | Role `platform-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `platform-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | pipeline-hardening | 3 (label 1.3) | medium reasoning; checksum verification | anthropic/claude-opus-5-5 | default | Role `platform-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `platform-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | pipeline-hardening | 4 (label 1.4) | high reasoning; a control must not be able to ship | anthropic/claude-opus-5-5 | default | Role `platform-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `platform-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | pipeline-hardening | 5 (label 1.5) | medium reasoning; packaging | anthropic/claude-opus-5-5 | default | Role `platform-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `platform-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | hosted-heartbeat | 1 (label 1.1) | medium reasoning; mode boundary | anthropic/claude-opus-5-5 | default | Role `backend-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `backend-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | hosted-heartbeat | 2 (label 1.2) | medium reasoning; storage query on both backends | anthropic/claude-opus-5-5 | default | Role `backend-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `backend-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | hosted-heartbeat | 3 (label 1.3) | low reasoning; plain HTML/JS; follows the role-bound UI skill | anthropic/claude-sonnet-5-5 | default | Role `frontend-engineer` owns these files; sonnet-class is enough for bounded docs, UI or config | Claude Code subagent `frontend-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | hosted-heartbeat | 4 (label 1.4) | medium reasoning; code reading | anthropic/claude-opus-5-5 | default | Role `backend-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `backend-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | hosted-heartbeat | 5 (label 1.5) | high reasoning; secrets placement and pod security | anthropic/claude-opus-5-5 | default | Role `platform-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `platform-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | go-live-docs | 1 (label 1.1) | medium reasoning; contract wording | anthropic/claude-sonnet-5-5 | default | Role `documentation-specialist` owns these files; sonnet-class is enough for bounded docs, UI or config | Claude Code subagent `documentation-specialist` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | go-live-docs | 2 (label 1.2) | low reasoning; runbook | anthropic/claude-sonnet-5-5 | default | Role `documentation-specialist` owns these files; sonnet-class is enough for bounded docs, UI or config | Claude Code subagent `documentation-specialist` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | go-live-docs | 3 (label 1.3) | low reasoning | anthropic/claude-sonnet-5-5 | default | Role `documentation-specialist` owns these files; sonnet-class is enough for bounded docs, UI or config | Claude Code subagent `documentation-specialist` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | go-live-docs | 4 (label 1.4) | low reasoning; no names or addresses | anthropic/claude-sonnet-5-5 | default | Role `documentation-specialist` owns these files; sonnet-class is enough for bounded docs, UI or config | Claude Code subagent `documentation-specialist` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | go-live-boundary | 1 (label 1.1) | high reasoning; oracle design | anthropic/claude-opus-5-5 | default | Role `qa-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `qa-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |
| sellbird-go-live | go-live-boundary | 2 (label 1.2) | high reasoning; live read-only checks plus one approved pod delete | anthropic/claude-opus-5-5 | default | Role `qa-engineer` owns these files; opus-class for trust-boundary, storage or pipeline work | Claude Code subagent `qa-engineer` | subagent type listed in this session on 2026-11-22; model as that role's definition sets it |

## CONTRACT BINDING

- Contract: `.kbd-orchestrator/phases/sellbird-go-live/adopted-contract.json` (adopted 2026-11-22).
- Identity: project `09d97122-c2c7-452a-a0a1-48a80e6cfef5`, run `postgres-gke-deployment-20261118T052720Z`, phase `sellbird-go-live`, plan revision 1.
- Budgets: 720 minutes, 2000 tool calls, 3 repair attempts, stop after 3 attempts without progress.
- Freshness: each scenario lists the files whose change invalidates its evidence.

## SCENARIO → TASK COVERAGE

| Scenario | What it shows | Owner tasks | Passes when | Negative control must show |
|---|---|---|---|---|
| SCN-REG-001 | Test suite green with the new rules covered | `hosted-small-fixes/1+hosted-small-fixes/2+hosted-small-fixes/3+hosted-heartbeat/1+hosted-heartbeat/2+hosted-heartbeat/3` | zero failures and every required test ID collected and passed | in each worktree the required tests of that task fail, and only those |
| SCN-FRESH-001 | Migration Job has what it needs before the sync | `hosted-persistent-home/2+hosted-persistent-home/3` | the Job's ServiceAccount is a PreSync hook with a lower wave than the Job; port 53 egress peers are exactly kube-dns pods and 169.254.20.10/32 | the check exits non-zero on each, naming the ServiceAccount and the unexpected peer |
| SCN-LOCK-001 | Image installs only hash-locked dependencies | `pipeline-hardening/5` | the build succeeds from the committed lock and the stale-lock check exits zero | (a) the build fails in the dependency install step; (b) the stale-lock check exits non-zero |
| SCN-PIPE-001 | A failing test run cannot deploy | `pipeline-hardening/1+pipeline-hardening/4` | static: publish and deploy each need the tests job and the scan job, neither has an if that lets it run after a failed need (no always(), !cancelled() or failure()), and no other workflow deploys on push; dynamic: the tests job concludes failure | (a) the graph check exits non-zero naming the job; (b) the tests job concludes success, showing the control input is what failed the run. No control run, including none, can publish or deploy |
| SCN-PIPE-002 | The scanned image is the published image, and a failing scan stops it | `pipeline-hardening/2+pipeline-hardening/3+pipeline-hardening/4` | static: the image-ID and save steps precede every scan step, a recheck step follows the last scan, and publish needs the scan job with no if that survives its failure; dynamic: in that run the vulnerability scan step concludes failure | (a) exits non-zero before any scan; (b) exits non-zero and reports the ID mismatch |
| SCN-SHIP-002 | A merge reaches the cluster with both containers ready | `hosted-heartbeat/5+hosted-persistent-home/1+go-live-docs/1+go-live-docs/4` | the digest the Deployment runs equals that GitHub-recorded digest, 2 of 2 containers are ready and the claim is Bound | the check exits non-zero on the digest mismatch |
| SCN-LIVE-001 | The hosted Sellbird runs heartbeat cycles | `hosted-heartbeat/1+hosted-heartbeat/2+hosted-heartbeat/5+go-live-docs/2` | at least one heartbeat row is newer than the pod's start time within three heartbeat intervals, and status reports running | status reports not running |
| SCN-LIVE-002 | Hosted configuration survives a restart | `hosted-persistent-home/1` | the SHA-256 of /data/sellbird.local.yaml and the SHA-256 of /data/.golive-marker are each identical before the delete and in the new pod | the script reports FAIL for that run, showing the comparison detects a file that did not persist |
| SCN-LIVE-003 | Nothing is sent without approval | `hosted-heartbeat/5+go-live-boundary/2` | the sent count is unchanged, approval mode is on, and any new row is pending review | the test transport records exactly that one item as sent, showing the count moves when approval is given; the live pause is untouched |

Tasks with no scenario of their own: `go-live-docs/3` (CHANGELOG), `go-live-boundary/1` (the scripts themselves) and `hosted-heartbeat/4` (the secret-split finding). All three are read at the cumulative review.

Required test IDs for SCN-REG-001: each of `hosted-small-fixes/1`, `/2`, `hosted-heartbeat/1`, `/2` and `/3` names its new tests in its change's `tasks.md` when done; `go-live-boundary/1` copies those IDs into `fixtures/golive-required-tests.txt`. Scratch copies for negative controls are made by `git worktree add` into a temporary folder, patched there and removed afterwards; the working tree is never patched.

Freshness: each scenario's invalidating files are its `invalidationKeys` in the contract.

## BOUNDARY PACKET (single run, post-implementation only)

1. `preflight` (build): `bash scripts/boundary/golive/preflight.sh`
2. `build` (build): `docker build -t sellbird:golive .`
3. `run-standin` (run): `bash scripts/boundary/golive/standin-up.sh`
4. `scn-suite` (scenario): `bash scripts/boundary/golive/suite.sh` → SCN-REG-001
5. `neg-scn-reg-001` (negativeControl): `bash scripts/boundary/golive/neg-reg.sh` → SCN-REG-001
6. `scn-fresh` (scenario): `bash scripts/boundary/golive/fresh-install-order.sh infra/k8s/base` → SCN-FRESH-001
7. `neg-scn-fresh-001` (negativeControl): `bash scripts/boundary/golive/neg-fresh.sh` → SCN-FRESH-001
8. `scn-lock` (scenario): `bash scripts/boundary/golive/locked-install.sh` → SCN-LOCK-001
9. `neg-scn-lock-001` (negativeControl): `bash scripts/boundary/golive/neg-lock.sh` → SCN-LOCK-001
10. `scn-pipe-graph` (scenario): `bash scripts/boundary/golive/pipe-graph-check.sh .github/workflows` → SCN-PIPE-001, SCN-PIPE-002
11. `neg-scn-pipe-graph` (negativeControl): `bash scripts/boundary/golive/neg-pipe-graph.sh` → SCN-PIPE-001
12. `scn-pipe-tests` (scenario): `bash scripts/boundary/golive/pipe-control.sh failing-test` → SCN-PIPE-001
13. `neg-scn-pipe-001` (negativeControl): `bash scripts/boundary/golive/pipe-control.sh none` → SCN-PIPE-001
14. `scn-pipe-scan` (scenario): `bash scripts/boundary/golive/pipe-control.sh vulnerable-image` → SCN-PIPE-002
15. `neg-scn-pipe-002` (negativeControl): `bash scripts/boundary/golive/neg-trivy-checksum.sh` → SCN-PIPE-002
16. `neg-scn-pipe-002-swap` (negativeControl): `bash scripts/boundary/golive/neg-image-swap.sh` → SCN-PIPE-002
17. `neg-scn-lock-001-stale` (negativeControl): `bash scripts/boundary/golive/neg-lock-stale.sh` → SCN-LOCK-001
18. `scn-ship` (scenario): `bash scripts/boundary/golive/live-rollout.sh` → SCN-SHIP-002
19. `neg-scn-ship-002` (negativeControl): `bash scripts/boundary/golive/live-rollout.sh --expect-previous-digest` → SCN-SHIP-002
20. `scn-live-restart` (scenario): `bash scripts/boundary/golive/live-restart.sh` → SCN-LIVE-002
21. `neg-scn-live-002` (negativeControl): `bash scripts/boundary/golive/live-restart.sh --marker-dir /tmp --expect-fail` → SCN-LIVE-002
22. `scn-live-heartbeat` (scenario): `bash scripts/boundary/golive/live-heartbeat.sh` → SCN-LIVE-001
23. `neg-scn-live-001` (negativeControl): `bash scripts/boundary/golive/neg-heartbeat-stale.sh` → SCN-LIVE-001
24. `scn-live-nosend` (scenario): `bash scripts/boundary/golive/live-nosend.sh` → SCN-LIVE-003
25. `neg-scn-live-003` (negativeControl): `bash scripts/boundary/golive/neg-approved-send.sh` → SCN-LIVE-003
26. `redaction` (scenario): `bash scripts/boundary/golive/redaction-grep.sh` → SCN-LIVE-001, SCN-LIVE-002, SCN-LIVE-003, SCN-SHIP-002

The suite, ordering, lock and pipeline commands need no cluster access. The `live-*` commands run against the live cluster after the operator steps below. Evidence goes to a new dated folder under `evidence/`.

## OPERATOR STEPS (asked once, at dispatch)

1. Operator says yes to an agent pushing the go-live branch and opening the pull request; the first tests and images runs happen on that pull request and on main after the merge.
2. Operator merges the Sellbird go-live pull request (after CI is green).
3. Operator merges or approves the platform overlay change that points at the new base, and creates the provider secrets through the platform's secret path.
4. Operator trains the hosted Sellbird (the `sellbird train` command, run by kubectl exec against the product's website) and confirms the Claude login works.
5. Operator approves one pod delete for SCN-LIVE-002 and the three workflow_dispatch control runs (failing-test, none, vulnerable-image).
6. Sending stays paused on the live Sellbird for the whole boundary run; the approved-send control runs on the local stand-in with a test transport.

Personal data: `redaction-grep.sh` is a supplementary check only. The blocking check is a read of the full phase diff and every commit message for real names, addresses, phone numbers and business domains, done at the cumulative review.

Not asked of the operator, and not done by agents: reading or printing any secret; entering passwords or codes; changing the `main` ruleset or code owners.

## LIMITS OF THIS PLAN

- The public host resolving, serving TLS and requiring a session (carried goals CG-1 to CG-3 of the last phase) were verified by the platform phase. This phase does not re-run them beyond what the live scenarios touch.
- SCN-PIPE-001 and SCN-PIPE-002 rest on a static reading of the workflow's job graph plus one control run each. A control run cannot publish or deploy by design, so the proof that a failed gate blocks the real path is the static graph check, not the control run.
- SCN-FRESH-001 is a static ordering check. A real install into an empty namespace is not run.
- SCN-LIVE-001 is BLOCKED, not failed, if the hosted Sellbird has not been trained or the Claude login does not work.
- SEC-02 and the deploy App's push scope are requested from the platform; this phase can close with them still open there.
- The hosted Sellbird will not send email at the end of this phase: sending stays paused until the operator chooses a mailbox and resumes it.

## COMMANDS TO RUN

- Adopt: `kbd-contract-adopt.sh .kbd-orchestrator/phases/sellbird-go-live/adopted-contract.json` (after the operator's yes).
- Readiness: `kbd-phase-readiness-check.sh --phase sellbird-go-live`.
- Then `/kbd-execute sellbird-go-live`.

## ADVERSARIAL REVIEW

Independent review by `mimo-v2.6-pro` through the local gateway, two rounds (the limit). The tool records the cross-model check as `unverified-producer-unknown`, because this session's model has no identity entry in the model configuration.

- Round 1: BLOCK. 4 CRITICAL, 8 WARNING. Two CRITICALs were real and fixed (the no-send control contradicted the sending pause; the image recheck had no tamper control). Two were wrong: SEC-04 and SEC-05 are in `pipeline-hardening`, and `.github/workflows/` exists. Both are now stated explicitly. All 8 WARNINGs were fixed.
- Round 2: BLOCK. 3 CRITICAL, 6 WARNING, all accepted as real and fixed: a static job-graph check now carries the proof for SCN-PIPE-001 and SCN-PIPE-002 (a control run cannot ship, so its skipped jobs proved nothing); SCN-REG-001's required tests are accepted at the cumulative review before the run and its negative control covers all five code tasks; SCN-LIVE-002 names its two values and its control now runs the same comparison on temporary storage; `sellbird/main.py` has one writer; F1-F3 are mapped; every control run is barred from publishing.

## UNRESOLVED REVIEW FINDINGS

The round-2 corrections have not been reviewed by the independent model. The operator is adopting a plan whose last set of fixes only its author has read. A third review round is available on request.
