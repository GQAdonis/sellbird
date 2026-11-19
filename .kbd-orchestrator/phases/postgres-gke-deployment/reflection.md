# Phase Reflection: postgres-gke-deployment

## Delta

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

## Root Cause

- **Live goals:** the platform the goals depend on was split out at assess (decision D11), and its phase hasn't run. The phase goals were never reworded to match, so "deploy to GKE" stayed a goal of a phase that could not deploy.
- **Boundary attempts:** the boundary depended on a large amount of harness code written in the same increment, none of it run before B4, as VLBV requires:
  - a multi-service stand-in;
  - a scripted Kratos sign-in with TOTP;
  - negative-control probes;
  - schema-dump oracles.
  - Most failures were in that harness, not in Sellbird. A repair limit of 2 didn't allow for a first run of that much untested harness.
- **Environment failures:**
  - The stand-in used the same default host ports (55432, 4456, 4433) as another local project built on the same images.
  - The repo's `.venv` lacked the `postgres` extra, which is a recurrence: the assessment had already found that the configured test command couldn't run in `.venv`.
- **False CRITICALs:** the review packets were built from the diff alone. Each false CRITICAL claimed behaviour that lives in unchanged lines the judge never saw. Examples: `translate_error` already sets `.sqlstate`; `design.md` moved the passthrough to the platform's auth host. The judge also saw a stale proposal sentence that contradicted the design, and it believed the proposal.
- **Runtime status:** the execute dispatch never ran `prometheus kbd phase transition --status in-progress`. The stage moved; the phase didn't.

## Corrective Actions

- **Next phase:** reword the live goals as the platform phase's own outcomes, plus a short Sellbird go-live phase after it, so each phase owns only what it can deliver.
- **Repair budget:** set the repair limit from the harness size at plan time. Count each new service in the stand-in, each scripted sign-in step and each new oracle family. A first run like this one needed 4–6 repairs.
- **Stand-in ports:** move the stand-in's host ports off the image defaults (follow-up F3), so it doesn't collide with other local projects.
- **Test environment:** install the `postgres` extra in `.venv` (`pip install -e '.[dev,postgres]'`) as part of the documented test command.
- **Review packets:** for diff reviews, include each changed function in full plus the functions it calls, and the design file of the change, not only the proposal.
- **Phase status:** move the runtime phase to in-progress when execute dispatches.
- **Ledger:** add task 10.5 to the ledger, or reconcile it as delivered, before the next phase starts.

## Contract Accuracy

| Metric | Value |
| --- | --- |
| Contract amendments after adoption | 7 (1 spec delta, 1 boundary-command fix, 1 implementation-complete, 4 repair-limit raises; all signed) |
| BLOCKED caused by the contract | 8 (7 test-oracle defects across attempts 6 and 7; 1 wrong entry point fixed before the run) |
| BLOCKED caused by the environment | 3 (port conflict, python3 shim, missing `postgres` extra) |
| NOT_EXERCISED scenarios | 0 (sub-checks not exercised: Trivy control end to end, live sync CG-1, hostname/TLS CG-2) |
| Repair attempts used / allowed | 6 / 6 (2 at adoption) |
| Post-closure escapes | 0 known (CI and the live path have not run) |
| Static QA / review findings at B4 step 5 (critical / warning) | QA 0 / 1; review 4 / 15, of which 0 / 3 survived checking |

Also in `accuracy.json`. Recurring constraint violation: `changelog-and-docs`, CHANGELOG.md (F2).

## Recalled Lessons

- **Recurred:** "the configured .venv test command cannot run" (assess summary). It came back in attempt 6 as a BLOCKED scenario: the `postgres` extra was missing from `.venv`.
- **Recurred:** "round-2 fixes not re-judged" (plan summary). The cumulative review again judged its own BLOCK without context. This time a confirmation review was run, and it repeated the same blind spot.
- **Applied:** include plan amendments in reviewer and judge packets. The repair-confirmation packet carried the original findings and the repair goals, so the judge reviewed against the amended criteria.

## Goals

| Goal | Status | Notes |
| ---- | ------ | ----- |
| G1: record the four decisions before build work | MET | D1–D12 in `assessment.md`, adopted at plan |
| G2: state layer on Postgres 18 (flint-forge), reversible migrations, least-privilege roles, invariants kept, move tool | MET | SCN-STORE-001..003, SCN-SEND-001/002, SCN-MOVE-001 PASS on the flint-forge PG18 image locally; single node only |
| G3: hardened image built, scanned and pushed to GHCR by digest on every merge | PARTIAL | Dockerfile and `images.yml` written; the image builds and its hardening checks pass locally (SCN-LOG-001, SCN-BRAIN-001). The workflow has never run, and nothing is in GHCR. The Trivy control's end-to-end run is NOT_EXERCISED |
| G4: production overlay and Argo CD apps on GKE, deploy job and protected main | PARTIAL | Manifests, example overlay, deploy guard and ruleset doc written (SCN-SHIP-001 against a scratch repo). The production overlay belongs to the platform repo by decision. No cluster sync; cluster facts unverified |
| G5: sellbird.know-me.tools resolves, serves TLS, requires a Kratos session via flint-gate; local mode unchanged | PARTIAL | Sign-in path proven against real Kratos and flint-gate containers (SCN-AUTH-001, 12 checks); local mode unchanged (SCN-AUTH-002). Hostname, DNS and TLS not exercised (CG-2) |
| G6: a harmless merge reaches the cluster end to end; independent security review; docs and CHANGELOG | NOT MET | No push, no pipeline run, no cluster. The security review and docs were done (SEC-01 and the quick fixes landed); SEC-02..05 are operator follow-ups |
| G7 (added at assess): platform interface contract | MET | `docs/platform-interface.md` plus its check script (SCN-CONTRACT-001); the platform repo's agreement is outside this phase |

Scenario level: 13 of 13 PASS, 0 FAIL, 0 BLOCKED, 0 NOT_EXERCISED (closure `c5381fb8`). Goal level: 3 MET, 3 PARTIAL, 1 NOT MET. The scenarios measure what can be proven locally; the goals ask for the live system.

## Delivered Changes

All by Claude Code project subagents under the sellbird-team, each archived after `openspec validate --strict` (commit `79bd9b3`):

- `baseline-test-green`: the test command runs green, with deterministic timing tests.
- `platform-interface-contract`: `docs/platform-interface.md`, the interface Sellbird and the platform repo build against, plus its check script.
- `postgres-storage-backend`: the psycopg 3 backend, versioned up/down migrations, the migrate and app roles, and the dialect translation.
- `hosted-gateway-mode`: gateway-mode authentication by JWT checked against JWKS, the loopback refusal kept for local mode, and no token in the logs.
- `sqlite-to-postgres-move-tool`: `sellbird storage move`, from an existing `data/sellbird.db` to Postgres.
- `cluster-ready-container-image`: a non-root, read-only image with a pinned Claude CLI and the brain reading its credential from the environment.
- `sellbird-gateway-route-config`: the flint-gate route and the local Docker stand-in (flint-forge, Kratos with TOTP, flint-gate, Sellbird).
- `image-build-scan-publish`: `images.yml`, which builds, scans (Trivy with a planted-secret negative control) and publishes by digest.
- `gitops-deploy-sellbird`: base manifests, the example overlay, NetworkPolicies, the deploy-bot guard and the ruleset doc.
- `hosted-mode-docs-and-review`: `docs/hosting.md`, the independent security review and its in-repo fixes.
- B5 repairs, outside the change list:
  - `39ab979`, `bf40883`, `f188920`: fixes to the build and the stand-in's sign-in script;
  - `1890b98`: the brain's stdout auth error;
  - `ebf4e3b`: test oracles;
  - `7c0a084`: three review findings.

## Technical Debt

- **F1:** `sellbird/storage_postgres/__init__.py` `PostgresBackend.exists` raises for a database that doesn't exist (`3D000` arrives at connect time without a SQLSTATE). Its docstring and the `_NOT_THERE` comment say it returns False.
- **F2:** no CHANGELOG entry for the stricter `exists()` behaviour or the value-free error strings (repair 6).
- **F3:** the stand-in in `infra/local/compose.yaml` uses the default host ports, which collide with other local stand-ins.
- `sellbird/auth/config.py` `_jwks_url` accepts `http://` JWKS addresses; it should require https outside loopback.
- `infra/k8s/base` NetworkPolicy DNS egress allows kube-dns only, so it would block GKE NodeLocal DNSCache if the cluster uses it.
- The migrate Job runs at PreSync, before the NetworkPolicies exist on a first sync.
- Dialect translation: `INSERT OR REPLACE` maps to an upsert that differs from SQLite when the conflict isn't on the primary key. Today's only caller is `settings`, where it doesn't matter.
- The Kratos stand-in serves over http; `docs/hosting.md` omits the PyYAML prerequisite.
- The Postgres CI job and `images.yml` have never run: first-run failures are likely.
- 12 leftover agent worktrees under `.claude/worktrees/`.
- History: earlier commits `85c4bea` and `cf2efcf` need the cleanup the operator listed before anything is pushed.

## Architecture Integrity

- AGENTS.md / CLAUDE.md violations: NONE found.
  - No real names, emails or domains in code, tests or docs: the boundary's SCN-SHIP-001 grep and the static QA pass both checked this. Test data uses `example.com` and `example.test`.
  - Secrets were never committed: the stand-in generates them into the ignored `infra/local/.env*`.
- Constraint violations: NONE blocking.
  - Static QA passed every blocking constraint; `refinement_log.md` has the details.
  - Warnings: design-system N/A; Windows acknowledged (the Postgres path is Linux-only); changelog-and-docs: F2 above.
- VLBV: generated code ran only at B4 and authorized B5s; the closure scan found no runner artifacts from before the authorization.

## Cross-Tool Coordination Notes

- **Progress tracking: GAPS FOUND.**
  - The runtime phase status stayed "pending" through execute.
  - Task 10.5 is missing from the ledger.
  - The position reminder's operator note still said `/kbd-assess` throughout execute.
- **Handoff quality: CLEAR, with one exception.** The per-round handoffs between subagents carried owner paths and commits well. The exception: the route-config proposal's stale passthrough sentence survived until archive and misled the review. Proposal text and design decisions drifted apart without anything flagging it.
- **Owner-only steps** stayed with the operator: amendment signatures, stopping another project's containers, merges. Twice that needed a round trip mid-run: the port conflict, and the permission check refusing to stop the other project's containers.

## Lessons Learned

- First boundary runs of a multi-service local stand-in written under VLBV fail mostly in the harness, not the product: set the repair limit at plan time from the harness size (here 6 were needed against 2 budgeted).
- Keep a stand-in's host ports off its images' defaults; another local project using the same images will already hold them.
- Install every optional extra the boundary tests need into the project's `.venv` as part of the documented test command, or the first run is BLOCKED on the environment.
- When a design decision overrides the proposal, edit the proposal in the same change; reviewers trust the proposal.
- [GLOBAL] Diff-only adversarial review packets produce false CRITICALs whenever correctness depends on unchanged code. Include each changed function in full, the functions it calls, and the change's design file.
- [GLOBAL] Check every judge CRITICAL against the code and the run evidence before acting on it. In this phase, 5 of 5 CRITICALs from a different-vendor judge were refuted by lines outside the diff, while 3 of its WARNINGs were real.
- [GLOBAL] Move the runtime phase to in-progress when execute dispatches. A phase left "pending" can't be closed, even with complete PASS evidence.
- [GLOBAL] `git worktree remove --force` can leave a stale `.git/index.lock`. Check for a live git process before removing it.

## Next Phase Seed

`phase-shared-platform` (in the new platform repo, per D11), then `phase-sellbird-go-live` in this repo:

1. **Platform repo:**
   - Gateway, flint-forge PG18 with Sellbird's database and roles, Kratos (operator-only, with MFA) and flint-gate on GKE;
   - provisioning that matches `docs/platform-interface.md`;
   - the production overlay.
2. **Go-live:**
   - history cleanup;
   - push and open a PR;
   - first runs of the CI matrix, the Postgres job and `images.yml` (fix first-run failures, including the Trivy control);
   - the GitHub App deploy bot and the protected-main ruleset.
3. **Live check:**
   - Argo CD syncs Sellbird by digest;
   - `sellbird.know-me.tools` resolves, serves TLS and requires a Kratos session (CG-1..3).
   - Also clear F1–F3, the JWKS https requirement and the NodeLocal DNS policy before the first sync.

## Codify as Skill?

- A "boundary harness preflight" checklist for VLBV stand-ins: free host ports, `.venv` extras, scripted-auth flows against the identity provider's real second-factor handoff, and oracle normalisation for custom Postgres images (for example `pg_attver`). Four of the nine attempts would have been saved.
- A review-packet builder that adds the full changed functions, their callees and the design file for diff mode.

## Context for Next Phase

Use this file as prior context for the next `/kbd-assess` invocation.
