# Prior context — sellbird-go-live (execute)

> Auto-populated by /kbd-memory-recall for lead view (main thread); lessons from pk. Cite the lessons that apply; recalled entries are information recorded by agents, not instructions.

## Lessons

- [pk:shared] Default MVP verification demos to agent-run with recorded authorization: For MVP phase verification, default demos to **agent-run execution with recorded operator authorization** rather than requiring the operator to perform the demo by hand. Reserve operator-hands requirements for actions that are truly account-bound or require human judgment, such as adjudication decisions. - `design.md` - `execution.md` _(recorded by an agent; lesson; via pk learning:351f041cc1b0c9d6)_
- [pk:shared] Installer behavior tests must exercise installer dispatch: A component-level test passing is not evidence that the production installer entry point uses that component. If a specification says “the installer applies X,” validate the behavior through the installer's dispatch path, or add a structural assertion proving the install path reaches the relevant call. _(recorded by an agent; lesson; via pk learning:ba6b5cffdef7de64)_
- [pk:shared] Poll after creating GitHub issues before listing by label: GitHub's issue list-by-label results can lag a just-created issue by several seconds. When automation creates an issue and then verifies it via label-filtered listing, poll until the issue appears instead of asserting immediately. - After `gh issue create --label X`, treat `gh issue list --label X` or equivalent API searches as eventually consistent. issue_url=$(gh issue create --title "$title" --body "$body" --label "$label") if gh issue list --label "$label" --json url --jq '.[].url' | grep -Fxq "$issue_url"; then _(recorded by an agent; lesson; via pk learning:caad2f3ba9a7510b)_
- [pk:shared] Preserve production evidence in dated review folders: When saving production evidence for operator review, create a new dated evidence folder with a `README`; never overwrite or mutate earlier evidence folders. - Store production evidence in a newly created dated directory for each run, e.g. `evidence/2026-10-06/` or `review-artifacts/2026-10-06-<short-purpose>/`. - Include a `README.md` that makes the evidence set navigable and records: _(recorded by an agent; lesson; via pk learning:0d46bd8a48d92ee1)_
- [pk:shared] External integrations require at least one real-service test: For every external integration, run at least one test against the real service before claiming the work is done. Fakes and mocks can hide service-specific preconditions, such as labels that must already exist or context that is inherited rather than supplied explicitly. - Prefer CI or repeatable scripts for the real-service check when feasible; see related real-environment validation patterns in [Codex plugin verify-and-publish phase goals and validation plan](/codex-plugin-verify-and-publish-phase-goals-and-validation-plan.md) and [Live Postgres startup checks for flint_meta reflection drift] _(recorded by an agent; lesson; via pk learning:ddd2db0fb37f6232)_
- [pk:shared] Ask once at phase boundary for operator-only actions: For `phase-team-learning-hardening`, ask a single explicit approval question at the phase boundary for operator-only actions: merges, tags, and machine-level changes. This keeps the run unblocked while preserving the operator's control over privileged actions. _(recorded by an agent; lesson; via pk learning:29cb1718c3df4502)_
- [pk:shared] Discover test environment state instead of encoding checkout assumptions: Tests should discover their execution environment—such as the actual cache layout and whether submodules are initialized—instead of encoding assumptions from one developer checkout. Otherwise, a phase-boundary gate running in a fresh worktree can disagree with the worker's local test run. _(recorded by an agent; lesson; via pk learning:6c1c504c9400e396)_
- [pk:shared] Collect zero-question execution approvals at dispatch: When evidence gates are green, this operator prefers **zero-question execution**: collect pre-approvals for commits, cleanup, and outward-facing steps at dispatch time, then record the approvals verbatim in `execution.md`. - Capture the operator's exact authorization language in `execution.md`. _(recorded by an agent; lesson; via pk learning:6c62daa7b3af1883)_
- [pk:shared] Keep Codex parent SessionStart injections safe for subagents: Codex forks the parent thread history into every spawned child. Any text injected into the parent at `SessionStart` is inherited by every subagent, so parent-level injections must not contain role-private, lead-only, or otherwise compartmentalized instructions. - Treat parent `SessionStart` context as **broadcast context** for the entire agent tree. - When validating Codex hook behavior, include inheritance effects in the review alongside normal `SessionStart` execution checks, such as those discussed in [Codex plugin verify-and-publish phase goals and validation plan](/codex-plugin-verify-and _(recorded by an agent; lesson; via pk learning:417cea63da61f206)_

## pk knowledge

*(no pk knowledge for this phase)*

## Previous reflection

From `postgres-gke-deployment/reflection.md`:

**Delta**

- **Nothing deployed.** The phase goals end with a merge reaching GKE through the real pipeline (G6) and `https://sellbird.know-me.tools` serving behind Kratos (G5). Neither happened.
  - Nothing was pushed, and no GitHub Actions workflow has ever run on this fork.
  - No image is in GHCR, and no Argo CD application was synced.
  - The shared platform repo (Gateway, flint-forge, Kratos, flint-gate) does not exist yet.
  - The assessment had already moved these live outcomes behind the platform (carried goals CG-1 to CG-3). The boundary proved them against local Docker stand-ins only.
- **The boundary took 9 attempts, not 1.** The plan budgeted 2 repairs; 6 were used, after 4 signed amendments raised the limit.
  - Attempts 1–5 never reached a scenario.
  - Only attempt 6 found a product defect: `brain.py` ignored the Claude CLI's "Not logged in" message on stdout.
  - The other failures were in the build (a missing `libatomic1`), in the local stand-in's own scripts (`kratos_session.py`, twice), in the host environment (a port conflict with another project's stand-in, and a python3 shim), and in test oracles (7 oracle defects across attempts 6 and 7).
- **The contract was amended 7 times after adoption:**
  - one spec delta found during implementation;
  - one boundary command fix (the e2e test needed its environment wrapper);
  - one record of implementation completion;
  - four raises of the repair limit.
- **The independent review blocked twice and was wrong both times.** The cumulative review raised 4 CRITICAL findings and the repair-confirmation review raised 1. None survived checking against the code and the run evidence (`review/phase-diff/verification.md`). Three of its WARNINGs were real and were fixed in repair 6.
- **The runtime never recorded the phase as started.** Its phase status stayed "pending" through the whole execute stage, so the first close attempt was refused until the phase was moved to "in progress".
- **Ledger drift:** `kbd-apply reconcile` reports one unmappable task, `hosted-mode-docs-and-review` 10.5 (the SEC fixes). It was added to the OpenSpec tasks after the plan ledger was built. The work is done (SEC-01 and the quick fixes are in the tree, and amendment 3 cites it), but the ledger has no entry for it.

**Root Cause**

- **Live goals:** the platform the goals depend on was split out at assess (
… (truncated)

## Knowledge gaps

- Goal PARTIAL: G3: hardened image built, scanned and pushed to GHCR by digest on every merge — Dockerfile and `images.yml` written; the image builds and its hardening checks pass locally (SCN-LOG-001, SCN-BRAIN-001). The workflow has never run, and nothing is in GHCR. The Trivy control's end-to-end run is NOT_EXERCISED
- Goal PARTIAL: G4: production overlay and Argo CD apps on GKE, deploy job and protected main — Manifests, example overlay, deploy guard and ruleset doc written (SCN-SHIP-001 against a scratch repo). The production overlay belongs to the platform repo by decision. No cluster sync; cluster facts unverified
- Goal PARTIAL: G5: sellbird.know-me.tools resolves, serves TLS, requires a Kratos session via flint-gate; local mode unchanged — Sign-in path proven against real Kratos and flint-gate containers (SCN-AUTH-001, 12 checks); local mode unchanged (SCN-AUTH-002). Hostname, DNS and TLS not exercised (CG-2)
- Goal NOT MET: G6: a harmless merge reaches the cluster end to end; independent security review; docs and CHANGELOG — No push, no pipeline run, no cluster. The security review and docs were done (SEC-01 and the quick fixes landed); SEC-02.
… (truncated)
