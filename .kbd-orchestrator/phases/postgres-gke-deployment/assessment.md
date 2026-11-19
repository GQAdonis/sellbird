ASSESSMENT: postgres-gke-deployment
Project: Sellbird
Date: 2026-11-17
Codebase baseline: Sellbird is a single-user, local-first Python app whose state lives in SQLite behind a pluggable `sellbird/storage.py` seam, served by a loopback-only FastAPI dashboard unlocked by a token link, with no container pipeline, CI history, rulesets or cluster deployment on this fork.
Cross-tool progress: none

Evidence sources: three read-only expert surveys run this stage (database-engineer, platform-engineer, gateway-engineer covering identity, gateway and AI credentials), the baseline test and build runs, and operator decisions recorded below. **No survey could query the GKE cluster:** the gcloud token on this machine has expired and needs an interactive `gcloud auth login` by the operator. All cluster facts here come from DNS and the know-meet repository's documentation and are UNVERIFIED until re-checked live.

Citation convention: unprefixed paths are in this repository. Paths prefixed `flint-forge@`, `flint-gate@` or `know-meet@` are in those read-only reference repositories (`~/Projects/prometheus/flint-forge`, `~/Projects/prometheus/flint-gate`, and a shallow clone of Know-Me-Tools/know-meet), read by the surveys at their current local HEADs; they are not in this repository and the review packet cannot resolve them. GitHub state (runs, rulesets, environments, secrets) comes from read-only `gh api` calls by the platform survey on 2026-11-17.

## Recalled lessons that shape this assessment

- "The operator merges every PR, wants the full KBD status at the end of every turn, and wants operator-only actions (tags, repos, live-data changes) asked explicitly." → Every outward action (GitHub settings, repo creation, cluster applies, DNS, secrets) is listed below as operator-approved, one at a time.
- "This operator prefers zero-question execution once evidence gates are green: collect pre-approvals (commits, cleanup, outward steps) at dispatch time and record them verbatim in execution.md." → The plan stage should gather pre-approvals at dispatch rather than mid-execution.
- "Default verification demos to agent-run with a recorded operator authorization; reserve operator-hands requirements for account-bound actions and judgment calls." → Account-bound steps (gcloud login, GitHub App key, secrets, setup-token) stay with the operator; everything else is agent-run with recorded authorization.

## Knowledge gaps

None recorded in prior-context.md.

## Operator decisions (recorded 2026-11-17, decision owner: the operator)

| # | Decision | Choice |
|---|---|---|
| D1 | SQLite for local installs | Keep SQLite as the default local backend; add Postgres as a second backend behind `sellbird/storage.py`; both run the same contract tests. |
| D2 | Where Postgres runs | One **shared** flint-forge PG18 instance (a platform service). Sellbird gets its **own `sellbird` database and least-privilege roles**, isolated from flint's `flint` database and other apps. |
| D3 | Dashboard protection | Operator-only sign-in with MFA: Kratos registration disabled, the operator identity created through the internal Kratos admin API, email+password plus TOTP/WebAuthn (aal2), and Sellbird accepts only allowlisted identities. Local token mode stays the default. |
| D4 | AI brain credential in the cluster | `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`, stored as a Kubernetes Secret the operator creates. **Risk owned by the operator:** whether headless server use of a subscription login is permitted by the provider's terms is not documented in this repo and was not verified. |
| D5 | Shared Envoy Gateway | Move `main-gateway` out of know-meet into a new shared platform repository. |
| D6 | flint-gate gaps | Work within current flint-gate: set `aud` via route additional claims, Sellbird ignores cookies and verifies iss/aud/kid strictly; Sellbird's flint-gate route config lives in this repo. No flint-gate repository changes. |
| D7 | Image pull | Make `ghcr.io/gqadonis/sellbird` public after first push. |
| D8 | Platform scope | Kratos, flint-gate and flint-forge Postgres are **shared** with other applications. The shared platform also includes **flint-realtime-fabric, ElectricSQL and Ory Hydra**. |
| D9 | Platform location | A **new platform repository** (outward action: creating it needs operator approval) with its own Argo CD AppProjects and its own KBD project. |
| D10 | Phasing | **Platform phase first**, in the new repo. This phase depends on it and narrows to Sellbird's own work. |
| D11 | Hydra | Platform-only. Sellbird keeps Kratos sessions checked by flint-gate. |
| D12 | Exclusions | Automated backups (wal-g/GCS), high availability, Codex in the cluster, and moving the operator's real local data are out of scope for this phase. |

### Consequence for the phase goals

Goals 4 and 5 as written assume this phase deploys Postgres, Kratos and flint-gate. Under D8–D10 those become platform-phase deliverables. The plan stage should restate the goals as follows (proposed; the operator adopts them at plan):

- **G4 (restated):** Sellbird's own Kustomize production overlay and AppProject-scoped Argo CD Application, consuming platform services through the interface contract (G7). Syncing it into the cluster is gated on the platform phase.
- **G5 (restated):** Sellbird's hosted gateway mode, its flint-gate route/claims config and its database/role definitions are delivered and verified against local stand-ins (a local Postgres 18 from the flint-forge image, a local Kratos + flint-gate via their compose files). The live check at `https://sellbird.know-me.tools` is **gated on the platform phase**.
- **G6 (restated):** In-phase end-to-end proof = a harmless merge to main produces a scanned image, the deploy bot pins `image@digest` in the production overlay through the protected ruleset, and Argo CD reports the Application synced to that digest **if the platform is live**; otherwise the proof stops at the pinned commit and the rendered manifests, and the live sync and sign-in check carry to the platform phase's closure. Independent security review and docs/CHANGELOG remain in-phase.
- **G7 (new, required):** Author and agree the platform interface contract with the new platform repository as counterparty: how Sellbird's database and role are provisioned on the shared Postgres, the flint-gate issuer/JWKS URL and minted-claims shape (`aud`, `sub`), the gateway listener/hostname and certificate ownership, secret names and namespaces, and Kratos identity provisioning. G4–G6 work that depends on the platform is dispatched only after G7 is agreed.

The platform phase is a hard prerequisite for the live parts of G4, G5 and G6.

IMPLEMENTATION STATUS
- Storage backend seam: PARTIAL — `sellbird/storage.py` (122 lines) already registers backends by locator and entry point (`storage.py:30,56,81-93`), but the contract is "aiosqlite-shaped" (`:14-18`) and `storage.IntegrityError` subclasses `sqlite3.IntegrityError` (`:34`). No Postgres backend exists.
- Schema and migrations: MISSING for Postgres — SQLite has 16 forward-only idempotent scripts versioned by `PRAGMA user_version` (`state.py:149-560,624-631`), 18 tables, 13 `ALTER TABLE ADD COLUMN`, no down-migrations. **There is no reversible-migration discipline to inherit:** G2's "versioned reversible migrations" must be introduced fresh for Postgres (up/down pairs, a version table replacing `PRAGMA user_version`, a tested downgrade path), while SQLite keeps its forward-only list.
- SQLite-specific SQL: PARTIAL portability — package-wide: 7 `INSERT OR IGNORE`, 1 `INSERT OR REPLACE` (`state.py:1459`), 5 `ON CONFLICT`, 13 `datetime('now')`, 4 `date('now')`, 5 `json_extract`, 1 `julianday` (`state.py:1210`), 2 `executescript`, 1 explicit `BEGIN` (`state.py:2008`). None of AUTOINCREMENT, ATTACH, FTS, `sqlite_master`, `lastrowid`.
- Code paths bypassing the seam: PARTIAL — `dashboard.py:1494` opens `sqlite3` read-only directly; `dashboard.py:833-840` runs `CREATE TABLE IF NOT EXISTS feedback` inline on every feedback write (incompatible with a non-owner app role).
- Signal governance: DONE on SQLite, MISSING on Postgres — a `BEFORE INSERT` trigger rejects unknown codes (`state.py:437-443`); needs a foreign key or plpgsql equivalent.
- Observation invariants: DONE on SQLite, UNASSESSED in detail for Postgres — facts are rows in `observations` with confidence and provenance, re-observation forms a time series, and only `status = 'confirmed'` signal codes are collected (per CLAUDE.md architecture notes and `state.py` schema). This stage verified the signal-code trigger but did not trace every enforcement point (transaction boundaries around observation writes, `state.cohort` set intersection). The Postgres contract-test scope must cover: unknown codes rejected, unconfirmed codes not collected, provenance/confidence persisted, and cohort results identical across backends.
- Outbox claim safety: DONE on SQLite, AT RISK on Postgres — compare-and-set on `status='sending'` checked via `rowcount == 1` (`state.py:1254-1270`) and a stale-claim sweep using `datetime()` (`state.py:1284`) rely on SQLite serialising writers. The heartbeat (`sellbird run`) and dashboard (uvicorn, `dashboard.py:3002`) are separate processes writing the same file.
- sellbird.db → Postgres move tool: MISSING.
- Hosted/gateway server mode: STUB — `workspace_home.py:18,61` already has `mode: "hosted"` (refuses CLI-brain features, `:113-125`), `build_app(guard=...)` exists (`dashboard.py` ~2961), and `Brain(transport=...)` is a documented hosted seam (`brain.py:99-106`). But `_check_loopback_bind` refuses any non-loopback host (`dashboard.py:2912-2925`) and there is no JWT-verifying guard.
- Dashboard token handling in a container: GAP — `start_dashboard` prints the unlock URL with `#token=` to stdout, which would land in cluster logs.
- Dashboard auth model: DONE for local — Host must be loopback, exact Origin and `Sec-Fetch-Site` checks, Bearer token in constant time, JSON-only bodies, two principals `user`/`agent` (`dashboard_auth.py:1-31,371-427`), token files owner-only (`:120-227`).
- Container image: PARTIAL — `Dockerfile` in this repo (python:3.12-slim, Playwright Chromium, non-root uid 1000, allow-list `.dockerignore`) exists, but installs the Claude CLI from an unpinned, unverified `https://claude.ai/install.sh` (not reproducible), assumes loopback health check and a writable `/app`. Image size is unmeasured (not built); Chromium and its system libraries are the expected largest layer.
- Image vulnerability scanning: MISSING — no scanner, fail threshold or scan gate exists. G3 requires a scanned image; the plan must choose a scanner (know-meet's workflow runs an artifact secret scan with a negative control), a severity threshold, and where the gate runs before push.
- CI image pipeline: MISSING — the only workflow is `.github/workflows/tests.yml` (present in this repo; the review packet's file tree omitted dot-directories); no images/deploy workflows.
- GitHub governance: MISSING (source: read-only `gh api` on GQAdonis/sellbird, 2026-11-17) — Actions enabled, 0 workflow runs ever on this fork, no rulesets, environments, secrets, variables or CODEOWNERS.
- Ruleset semantics for the deploy bot: TO DEFINE — in the reference pattern the deploy GitHub App has an `always` bypass on the main ruleset, so its pin commit is **not** subject to required reviews or status checks; protection comes from (1) the app having only Contents read/write on this one repo, (2) its key existing only as a `production` environment secret restricted to `main`, and (3) the deploy job's guards (SHA/digest regex, never-backwards, changed-lines-only diff). Human and other-actor pushes remain subject to the ruleset. G6's acceptance wording must say "pinned by the bot through its bypass, with all other writers subject to the ruleset", not "the pin is checked by the ruleset".
- Independent security review: MISSING — none exists for this phase. It must be performed by the `security-reviewer` role in a separate context from the implementers (read-only), over the storage backend, hosted gateway mode and JWT verification, flint-gate route/claims config, Kubernetes manifests, workflows and ruleset, and produce a severity-ranked findings record under `.agent-team/findings/security/` that the closure packet cites. CRITICAL/HIGH findings block closure.
- Kubernetes/Argo CD manifests for Sellbird: MISSING.
- Shared platform (Gateway, flint-forge Postgres, Kratos, Hydra, flint-gate, flint-realtime-fabric, ElectricSQL): MISSING on GKE per repo evidence; live state UNKNOWN (cluster unreachable). `flint-forge@deploy/helm/flint-forge` and `flint-forge@deploy/argocd/flint-forge-applicationset.yaml` target AKS/Azure only; `flint-gate@k8s/overlays/ssr` (its only overlay) targets AKS.
- Platform interface contract: MISSING — no agreed contract exists for database provisioning, issuer/JWKS, listener ownership, secret names or identity provisioning (see G7).
- Tenancy model: UNDECIDED — `workspace_home` suggests multiple workspaces; multi-user Sellbird is excluded, but whether Postgres row-level security applies inside the `sellbird` database is not decided. Proposed default for plan adoption: single tenant, RLS deferred, isolation by database and role (decision owner: the operator).

CROSS-TOOL PROGRESS
- NONE — no cross-tool activity recorded; `openspec/changes/` contains only `archive`.

SPEC GAP SUMMARY
- No canonical OpenSpec specs exist yet (`openspec/specs/` is empty), so there is no spec to align against; the phase must author capability specs (storage backend, hosted mode, deployment) before generation.
- flint-gate's minted JWT has no default `aud` (`flint-gate@crates/flint-gate-core/src/auth/jwt_mint.rs:262-293`) and forwards the browser Cookie upstream (`flint-gate@crates/flint-gate-core/src/middleware/pipeline.rs:1079-1120`); handled per D6 inside Sellbird.
- flint-forge image facts that affect a `sellbird` database (`flint-forge@images/postgres18/Dockerfile`): final stage `FROM postgres:18` (line 106) with pgrx extensions, pg_net, pg_cron, pgvector, pgcrypto, pg_graphql; `shared_preload_libraries=pg_net,pg_cron,flint_llm` with `cron.database_name=flint` and `pg_net.database_name=flint` (line 171); first-boot init writes into the default database. Sellbird should need none of these extensions.
- flint-forge publishing drift: Docker Hub `tribehealth/flint-forge-pg` (`flint-forge@.github/workflows/postgres-image.yml:38-64`) vs Helm default `prometheusags/flint-forge-pg:18` vs Azure overrides; `flint-forge@docs/postgres-extensions.md` is stale (says no pg_graphql, but `flint-forge@images/postgres18/Dockerfile:139` installs it). Platform-phase concern.
- Cluster networking (from docs, unverified): Envoy Gateway `main-gateway` (GatewayClass `eg`) owned by know-meet's Argo CD app; cert-manager ClusterIssuers via Cloudflare DNS-01; external-dns with **no domain filter** and upsert-only policy, so any hostname attached to the Gateway becomes a permanent public record.
- DNS: `know-me.tools` is on Cloudflare; `meet` → 8.236.202.95 (the Envoy LB); `auth` and `gate` already point to 23.239.29.33, a different host, so those names are unavailable; `sellbird` does not resolve.

BUILD HEALTH
- build check: PASS — `.venv/bin/python -m compileall -q sellbird && .venv/bin/python -c "import sellbird.cli"`, both exit 0 (2026-11-18).
- tests: FAIL (2 of 3,729) — `.venv` lacks pytest and pip; run with a temporary overlay (`uv run --no-sync --with pytest --with pytest-asyncio python -m pytest -q`): **3,700 passed, 2 failed, 27 skipped** in 13m10s. Failures: `tests/test_compliance_footer.py::test_a_long_french_reply_is_quick` and `tests/test_people_finder.py::test_nested_testimonials_are_bounded`. Both are timing-bounded tests; slowness from the external T7 volume is a hypothesis, UNVERIFIED. CI on GitHub has never run, so platform parity is UNKNOWN.
- known violations: the project virtualenv cannot run the test command in `project.json` (`.venv/bin/python -m pytest`) because dev extras are not installed; a hook blocks `uv pip install` and prefers `uv sync`.
- test coverage: PARTIAL — two different metrics: **3,729 collected test items** (the pytest run above: 3,700 + 2 + 27, including parametrized cases) versus **~2,047 test functions in 118 files** (the database survey's static count of `def test_` definitions), of which ~1,312 functions in 69 files construct SQLite databases on temp paths. `tests/test_storage.py` covers backend registration. No Postgres, hosted-mode or deployment tests exist.

CONSTRAINT CHECK
- AGENTS.md violations: N/A — `AGENTS.md` exists locally but is gitignored (`.gitignore:29`); its entire content is the managed `prometheus-team-routing` block written by the agent-team installer this session (routing pointer to `.agent-team/project-routing.json`), with no "Never Do" or other rules. Project rules come from CLAUDE.md and CONTRIBUTING.md via `.kbd-orchestrator/constraints.md`.
- constraints.md violations: **`tests-pass` (blocking) is already unsatisfied at baseline** — 2 tests fail, and the configured command `.venv/bin/python -m pytest -q` cannot run because the project virtualenv lacks the dev extras. The plan must carry a change that makes the baseline green and the configured test command runnable (or amends `project.json` with the operator's agreement) before any archive. `build-passes` (blocking): satisfied. No other violations observed in existing code. Forward risks: `sending-safety-preserved` (outbox claim semantics under Postgres), `dashboard-token-private` (token printed to stdout in containers), `codex-isolation-preserved` (unchanged; Codex excluded from the cluster), `untrusted-text-stays-untrusted` (unchanged), `no-hardcoded-secrets` (setup-token, Postgres, Kratos and flint-gate secrets must stay operator-created Secrets).

GOAL PROGRESS
- G1 Decide and record the four decisions: MET — D1–D4 recorded, plus D5–D12.
- G2 State layer on Postgres 18 (flint-forge image): NOT MET — seam exists; backend, migrations, invariant ports and move tool are missing.
- G3 Hardened image built, scanned and pushed to GHCR by digest: NOT MET — Dockerfile exists but is unpinned and loopback-bound; no pipeline.
- G4 Kustomize overlay and Argo CD Applications: NOT MET — restated above; live sync gated on the platform phase.
- G5 sellbird.know-me.tools behind Kratos/flint-gate: NOT MET — restated above; in-phase verification against local stand-ins, live check gated on the platform phase.
- G6 End-to-end proof with independent review: NOT MET — restated above with an in-phase definition that does not require the platform.
- G7 Platform interface contract (proposed): NOT MET — no contract exists.

## Risks and concerns

1. **Cluster state is unverified.** Every cluster fact is from docs; re-run the read-only survey after `gcloud auth login`.
2. **Outbox claim and company dedup depend on SQLite rowcount and writer serialisation** — the highest correctness risk for sending safety under Postgres with two writer processes.
3. **Brain credential terms (D4)** — headless subscription use is the operator's call; a long-lived token sits in the cluster with manual rotation.
4. **Platform dependency** — G5/G6 cannot complete until the new platform repo's phase delivers the shared services; this phase's plan needs a defined interface (database/role provisioning, gateway route contract, JWKS URL, hostname listener).
5. **external-dns has no domain filter** — any hostname attached to the shared Gateway is published permanently.
6. **CI has never run** — making checks required before they pass on main would block every PR.
7. **Unpinned Claude CLI install** makes images non-reproducible and unverifiable.
8. **Tenancy** — `workspace_home` suggests multiple workspaces; whether Postgres row-level security applies inside the `sellbird` database is undecided (proposed default: single tenant, RLS deferred; operator adopts at plan).
9. **Baseline red** — the blocking `tests-pass` constraint fails today (2 timing tests, and the configured command cannot run in `.venv`), so no change can archive until it is fixed.

## Adopted-outcome contract inputs

- **User operation (the one useful shipped operation):** The operator opens `https://sellbird.know-me.tools`, signs in with Kratos (password + second factor) through flint-gate, and uses Sellbird's dashboard backed by the `sellbird` database on the shared flint-forge Postgres; meanwhile a local install still runs on SQLite with the token link, unchanged.
- **Observed baseline:** local-only, SQLite-only, loopback-only dashboard; 3,700/3,729 tests pass locally with 2 timing failures; no image pipeline, CI history, rulesets or manifests; `sellbird.know-me.tools` does not resolve; cluster contents UNKNOWN (auth expired); shared platform not yet deployed on GKE per repo evidence.
- **Desired observable result — in scope for this phase (no platform dependency):** (a) Sellbird's full contract test suite passes against both SQLite and a local Postgres 18 from the flint-forge image, and the baseline is green; (b) a merge to main builds, scans and pushes `ghcr.io/gqadonis/sellbird@sha256:…` and the deploy bot pins it in the production overlay through the protected ruleset; (c-local) in gateway mode against local Kratos + flint-gate stand-ins, an unauthenticated request is refused/redirected and a valid gate-minted JWT for the allowlisted identity reaches the dashboard, while forged headers are rejected; (e) local token mode is unchanged; (f) the platform interface contract (G7) is agreed.
- **Desired observable result — gated on the platform phase (verified only once the shared Gateway, flint-forge Postgres, Kratos and flint-gate are live; otherwise carried to the platform phase's closure, not claimed here):** (c-live) Argo CD syncs Sellbird's Application and the pod runs the pinned digest; (d-live) `https://sellbird.know-me.tools` resolves, serves TLS, redirects an unauthenticated request to Kratos sign-in, and the authenticated operator reaches the dashboard.
- **Supported environments:** local: macOS, Linux, Windows with SQLite (existing CI matrix); hosted: GKE `gke_knowme-corporate_us-south1_main` behind the shared Envoy Gateway, flint-gate, Kratos and flint-forge PG18.
- **Required safety/security checks (non-waivable):** sending safety (approval default, quiet hours, limits, opt-outs, outbox claim exactly-once) preserved on both backends; unknown signal codes rejected on both backends; dashboard token never logged in any mode; gateway mode chosen only by config, never by request headers; Sellbird verifies gate JWT iss/aud/kid/exp against a pinned JWKS and allowlisted `sub`, ignores cookies and unverified `x-flint-*`/forwarded headers; NetworkPolicy so only flint-gate reaches Sellbird; least-privilege DB role with no DDL at runtime; no secrets in tracked files; independent security review of storage, auth, gateway and manifests; Codex isolation untouched.
- **Exclusions / deferred:** automated backups (wal-g/GCS); high availability and autoscaling; Codex in the cluster; migrating the operator's real local data; deploying the shared platform services themselves (moved to the platform phase in a new repo); flint-gate repository changes; Hydra integration for Sellbird; multi-user Sellbird.
- **Risk acceptance:** D4 terms risk accepted by the operator; single-replica availability accepted; manual secret creation and rotation accepted.
- **Decision owner:** the operator (repository owner).

## Value scenario frontier (proposals, not yet adopted)

| Candidate | Actor / outcome | Source | Reason now | Likelihood | Mandatory |
|---|---|---|---|---|---|
| SCN-STORE-001 | Local user's existing workflows keep working on SQLite after the backend split | assumption: D1 | Prevents regressing the upstream promise | high | yes |
| SCN-STORE-002 | Same contract suite passes on Postgres, including signal-code rejection | assumption: D1/D2 | Core of G2 | high | yes |
| SCN-SEND-001 | Two concurrent claimers never send the same outbox item twice on Postgres | assumption: sending safety | Highest correctness risk | UNKNOWN | yes |
| SCN-MOVE-001 | A fixture sellbird.db moves to Postgres with row counts and invariants preserved | assumption: G2 | Tool is in scope; real data excluded | medium | no |
| SCN-AUTH-001 | Unauthenticated request is sent to Kratos sign-in; forged `x-flint-*` header without valid JWT is rejected (local stand-ins in-phase; live hostname gated on platform) | assumption: D3/D6 | Public exposure | high | yes |
| SCN-AUTH-002 | Local token mode is unchanged and refuses non-loopback binds | assumption: D3 | Upstream behaviour | high | yes |
| SCN-SHIP-001 | A harmless merge produces a scanned image and a bot-pinned image@digest commit through the ruleset; live Argo CD sync checked only if the platform is live | goal G6 (restated) | End-to-end proof | medium | yes |
| SCN-BASE-001 | The configured test command runs and passes on the baseline | constraint tests-pass | Blocking constraint red at baseline | high | yes |
| SCN-LOG-001 | No dashboard token appears in container logs | constraint dashboard-token-private | Cluster logging | high | yes |

Calibration inputs unresolved: no owner-reviewed examples exist yet; the platform interface contract (database provisioning, JWKS URL, gateway listener) must be defined before SCN-AUTH-001 and SCN-SHIP-001 can be made executable.

## Operator actions identified (each needs separate, explicit approval)

1. Run `gcloud auth login` (operator) so the live read-only survey can be re-run.
2. Create the new shared platform repository (name and owner to be confirmed).
3. Make `ghcr.io/gqadonis/sellbird` public after first push.
4. Create a GitHub App (Contents read/write only) installed only on GQAdonis/sellbird.
5. Create the `production` environment with deployment branch policy `main`.
6. Set repository variable for the deploy app's client ID.
7. Set the deploy app's private key as an environment secret (operator runs `gh secret set … --env production`).
8. Apply the main ruleset with the app's `always` bypass — only after tests are green on main and the deploy job has merged.
9. Apply Sellbird's Argo CD AppProject(s) and Application(s).
10. Add the `sellbird.know-me.tools` listener and Certificate on the shared Gateway (publishes a permanent DNS record via external-dns).
11. Create Kubernetes Secrets by hand: Sellbird DB credentials, `CLAUDE_CODE_OAUTH_TOKEN`, gate JWKS/issuer config as needed.
12. Create the operator's Kratos identity through the admin API and enrol a second factor.

## Adversarial review

Judge: `mimo-v2.6-pro` over the REST gateway, producer `claude-opus-5-5`; recorded `cross_model_check: unverified-producer-unknown` because the packet carries no canonical producer identity tuple (stated, not hidden). Round 1 (`review/assess/findings-round1.json`): BLOCK, 1 CRITICAL / 6 WARNING / 2 SUGGESTION — all addressed (gated outcomes split out, G4–G7 restated/added, tests-pass recorded as red, build check run, external citations namespaced, GitHub-state source stated, migration policy and tenancy recorded). Round 2 (`review/assess/findings.json`): BLOCK, 1 CRITICAL / 5 WARNING / 2 SUGGESTION — warnings and suggestions addressed in this revision (observation invariants, scanning gap, ruleset bypass semantics, AGENTS.md content, security-review definition, test metrics, image size).

## Unresolved review findings

- **[CRITICAL, round 2] ".github/workflows/tests.yml is not visible in the packet, so the CI gap rests on an unverifiable premise."** Not accepted as a defect of the assessment: the packet builder's file tree omits the `.github` directory. Local evidence on 2026-11-18: `ls .github/workflows` → `tests.yml`; the file's matrix is ubuntu/macos/windows × Python 3.11/3.12 and it has never run on this fork (0 runs per `gh api`). The "existing CI matrix" claim refers to the workflow definition, not to run history; run history is recorded separately as zero. Carried forward so the analyze/plan stages can re-check it.

ASSESSMENT COMPLETE
