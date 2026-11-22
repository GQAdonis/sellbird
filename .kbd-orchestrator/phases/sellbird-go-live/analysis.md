# Analysis — sellbird-go-live

Written 2026-11-22. This phase needs almost no outside research: the open questions are about Sellbird's own code and manifests. Research budget used: no external queries; one tool check (`uv 0.11.9` is installed).

## Lessons applied

- "Installer behavior tests must exercise installer dispatch" and "Boundary gates must launch the packaged artifact": every design below is judged by whether the published image, started by its real entrypoint in the cluster, does the thing.
- "External integrations require at least one real-service test": the heartbeat's first cycle is checked against the live database and the real Claude login, not a stand-in.

## Findings from the code

Every path below is in the working tree of this checkout (`/infra/k8s/base/`, `/.github/workflows/`, `/sellbird/`, `/Dockerfile`), read on 2026-11-22 on branch `fix/gateway-mode-session-cookie`, whose tree matches `origin/main` at `a661932` for these files. Copies under `.claude/worktrees/` are leftovers from earlier agent runs and were not used.

1. **The hosted pod loses its configuration on every restart.** `infra/k8s/base/deployment.yaml` mounts `/data` (`SELLBIRD_HOME`) as an `emptyDir`. `sellbird/home.py` `seed_home` copies the shipped defaults into it on each start, and only files that are missing: the loop skips any destination that exists (`if dest.exists() or dest.is_symlink(): continue`), and its docstring says it never overwrites. Training (`sellbird/trainer.py`) writes `sellbird.local.yaml` and `skills/product_knowledge.md` there; dashboard settings write the same config file (`sellbird/config.py` around line 1198). So training, the offer, autopilot and send settings do not survive a restart or a deploy.
2. **The heartbeat refuses to start in a pod.** `sellbird/main.py` `_needs_setup` returns True when `<home>/.env` does not exist. The pod receives secrets as environment variables and has no `.env`, so `sellbird run` and the dashboard's `POST /api/sellbird/start` both report "not set up" even after training.
3. **The dashboard can already launch the heartbeat**, as a child process (`sellbird/dashboard.py` `start_sellbird`). In a pod that child dies with the container and nobody restarts it, so it is not a way to keep Sellbird running.
4. **One writer is assumed.** `sellbird/pidfile.py` stops a second heartbeat on the same machine. The migration runner takes a Postgres advisory lock; the heartbeat does not. Two pods would both run cycles.
5. **Provider secrets have one path in.** The Deployment reads single keys with `secretKeyRef` (database URL, Claude token, gateway settings). Mailbox, verifier and discovery keys have no entries yet.
6. **Nothing in the dashboard runs training.** `sellbird train <url>` is a CLI command only.
7. **Fresh-install deadlock, confirmed in the manifests.** `migrate-job.yaml` is a PreSync hook at wave -1 with `serviceAccountName: sellbird`. `serviceaccount.yaml` is an ordinary resource, applied in the sync that the hook must finish before.
8. **SEC-03, this repo's part.** In `.github/workflows/images.yml` the `deploy` job needs only `images`; `tests.yml` is a separate workflow, so a red test run does not stop a deploy. Both checkouts I found already set `persist-credentials: false`.
9. **SEC-05.** The Dockerfile installs `requirements.txt` (24 lines of ranges) plus two extras lists read from `pyproject.toml`, with no hashes.

10. **SEC-04, confirmed in this checkout.** In `.github/workflows/images.yml` the Trivy scans run at lines 195-248 through `aquasecurity/trivy-action`, pinned by commit SHA, with the scanner version set by `SCANNER_TRIVY_VERSION`. The image ID is first read at line 267 (`docker image inspect`) in the save step, after those scans, and the image is saved at line 269. The publish job then checks the loaded image against that ID (lines 316-322). So the ID that publish trusts is taken after third-party scan steps had Docker access. The action downloads the Trivy binary without a checksum this workflow controls.
11. **JWKS rule.** `sellbird/auth/config.py` `_jwks_url` accepts scheme `http` or `https` for any host.
12. **F1.** `sellbird/storage_postgres/__init__.py` `exists()` returns False when the error's `sqlstate` is `3D000` or `42P01`, and re-raises otherwise. A missing database reported at connect time may carry no `sqlstate`; that case has no test.
13. **F2.** `CHANGELOG.md` has no entry for the stricter `exists()` or the value-free error text.
14. **F3.** `infra/local/compose.yaml` publishes flint-gate on a fixed `127.0.0.1:4456`; the Postgres and direct ports are already variables.

## Design calls

| # | Question | Call | Why | Rejected |
|---|---|---|---|---|
| A1 | Where hosted configuration lives | A small persistent volume for `/data` (one `PersistentVolumeClaim`, ReadWriteOnce) | Training, the offer and settings already write files there; a volume keeps all of them with no code change, because `seed_home` never overwrites an existing file (finding 1). One replica makes ReadWriteOnce safe. Cost is a few cents a month. | Moving configuration into Postgres: correct long term, but it rewrites the config loader, the trainer and every settings endpoint. A ConfigMap in the platform repo: dashboard edits could not be saved. |
| A2 | How the heartbeat runs | A second container in the same pod running `sellbird run`, sharing `/data` | Kubernetes restarts it; it reads the same config and skill files as the dashboard; one pod keeps the one-writer assumption. | A second Deployment: cannot share a ReadWriteOnce volume across nodes reliably. The dashboard's start button: dies on restart. |
| A3 | Setup check in a pod | In hosted mode, `_needs_setup` stops requiring a `.env` file and checks the trained config only | Secrets arrive as environment variables there. Local mode is unchanged. | Writing a dummy `.env` into the volume: hides the real condition. |
| A4 | Dashboard "running" status | In hosted mode, report running only when the heartbeat's most recent cycle record in the database is newer than three heartbeat intervals (45 minutes at the default 15), otherwise "not running since <time>"; hide start/stop. The plan's first task for this change names the existing table the loop already writes each cycle (the action log in `sellbird/state.py`), or adds one timestamp row if the loop writes nothing on an idle cycle | The two containers have separate process tables, so the pidfile check cannot see the heartbeat. | Sharing the process namespace: weakens isolation between the public-facing container and the one holding mailbox credentials. |
| A5 | Provider secrets | Optional `secretKeyRef` entries (`optional: true`). Both containers: database URL, gateway settings. Heartbeat only: Claude token, mailbox, verifier and discovery keys. If the plan's first task finds a dashboard action that sends mail or calls a provider directly, that key is added to the dashboard too and the plan says which | Matches the existing pattern; the dashboard, which faces the internet, holds fewer secrets. The secrets themselves are created by the operator through the platform's secret path. | Mounting a `.env` file from a Secret: gives every key to both containers. |
| A6 | Training in hosted mode | Documented operator command: `kubectl exec` into the heartbeat container and run `sellbird train <url>` | Smallest change; the result lands on the persistent volume. | A training screen in the dashboard: real value, but a new feature with its own UI and abuse surface; propose as a follow-up. |
| A7 | Migration Job account | The Job runs under its own ServiceAccount that is itself a PreSync hook at an earlier wave | Fixes fresh installs without touching the app's account. | Running the Job as `default`: breaks if the namespace restricts the default account. |
| A8 | Gate deploys on tests | Merge the test jobs into the path to `deploy`: `images.yml` calls `tests.yml` as a reusable workflow and `deploy` needs it | A single workflow gives a hard dependency. | `workflow_run` chaining: runs from the default branch's file and is easy to get subtly wrong. |
| A9 | Hash-locked dependencies | Adopt `uv pip compile --generate-hashes` to produce one tracked file, `requirements.lock`, from `pyproject.toml` with the `hosted` and `postgres` extras; the image installs it with `pip install --require-hashes`; CI fails when the file is stale. `requirements.txt` stays as the unlocked developer file | `uv` is already on the machine; the output is a plain requirements file, so the image build keeps `pip`. | `pip-tools` (`pip-compile --generate-hashes`): equivalent output, one more tool to install. Building the image from `uv.lock`: that file is untracked in this checkout and would put `uv` inside the image build. Hand-maintained hashes. |
| A11 | SEC-04 and the Trivy control | Record the image ID immediately after the build step and save the image to a tar; after all scans, recompute the ID and fail on mismatch; publish from the saved tar. Verify the Trivy binary against a checksum pinned in the workflow. Prove the gate with a control run: a workflow-dispatch input that scans a known-vulnerable image through the same steps and must fail before publish | Closes the window in which a scan step with Docker access could swap the image, and shows the scan can actually stop a release. | Trusting the pinned action alone: the action is pinned, the binary it downloads is not. |
| A12 | JWKS https rule | Require `https` unless the host is loopback or ends in `.svc` or `.svc.cluster.local` | The cluster's JWKS address is an in-cluster service over plain http by platform design; anything else must be encrypted. | Requiring https everywhere: breaks the deployed configuration. |
| A13 | F1 | `exists()` returns False only for an error whose `sqlstate` is `3D000` or `42P01`. A connect failure with no `sqlstate` always raises, whatever its message, and the docstring and the `_NOT_THERE` comment are corrected to say exactly that. A test pins the missing-database case at connect time | Error text is not a safe discriminator, so an unclassified connect failure is treated as an outage. This keeps "an outage is never mistaken for an empty install". | — |
| A14 | F2, F3 | One CHANGELOG entry; a `SELLBIRD_LOCAL_GATE_PORT` variable for the flint-gate port | Mechanical. | — |
| A15 | Hosted-mode signal | The existing `SELLBIRD_DASHBOARD_MODE=gateway`, set on both containers from the `sellbird-gateway` ConfigMap | Already the only switch for hosted behaviour (`build_gateway_app`); no second flag to drift. | A new `SELLBIRD_HOSTED` variable. |
| A16 | DNS egress with NodeLocal DNSCache | In `infra/k8s/base/networkpolicy.yaml`, keep the existing rule (UDP and TCP 53 to pods labelled `k8s-app: kube-dns`) and add a second egress rule for UDP and TCP 53 to `169.254.20.10/32`, the link-local address GKE's NodeLocal DNSCache listens on. The pod's `dnsPolicy` is unchanged | With NodeLocal DNSCache on, pods send DNS to that address and the current rule would drop it; with it off, the extra rule matches nothing. The metadata server at `169.254.169.254` stays blocked. | Allowing all of `169.254.0.0/16` on port 53: wider than needed. |
| A10 | Mail provider for hosted | Operator decision, not made here | Gmail's sign-in needs a browser on the machine; SMTP+IMAP needs only secrets and suits a pod best. | — |

## Library candidates

One adoption (A9, `uv` for lock generation). Everything else is built in this repo. See `library-candidates.json`.

## Knowledge gaps

From prior context: G3–G6 of the last phase, now delivered or reported delivered (see the assessment). `/learn-goal` is available on request for any of them.

## Open questions

- A10: which mail provider and verifier the hosted Sellbird uses, and which product it is trained on. The plan's scenarios are written so they do not depend on the answer: sending stays paused during verification.
- Whether the cluster runs NodeLocal DNSCache. A16 allows both cases.
- Whether the Claude token in the cluster's `sellbird-claude` secret is a working login. The first heartbeat cycle will show it.
- Storage class for the volume: the base leaves it to the cluster default; the platform overlay may pin it.

## Readiness

| Call | Contract section it feeds | New runtime code |
|---|---|---|
| A1, A2, A5, A7 | scenario matrix: hosted operation, fresh install | manifests only |
| A3, A4 | scenario matrix: hosted operation | yes, small, hosted mode only |
| A6 | exclusions (dashboard training), operator steps | docs only |
| A8, A9, A11 | scenario matrix: supply chain | workflow and Dockerfile |
| A12, A13, A14, A15, A16 | scenario matrix: hosted operation; regression controls | yes, small |
| A10 | operator inputs | none |

**READY to spec.** Nothing is blocked. A10 is needed before the hosted Sellbird sends anything, not before planning or building.

## Review record and unresolved findings

Independent review by `mimo-v2.6-pro`; two rounds, the limit.

- Round 1: BLOCK, 3 CRITICAL (file sources unclear, the volume claim unverified, no design calls for SEC-04, the JWKS rule and F1-F3). All corrected.
- Round 2: BLOCK, 1 CRITICAL (no design call for the DNS policy) and 3 WARNINGs (no staleness bound in A4, no discriminator in A13, SEC-04 facts deferred). All corrected above as A16, A4, A13 and finding 10.
- **Unresolved:** the round-2 corrections were not reviewed again. Two points stay open for the plan: A4 has not yet named the table the heartbeat writes each cycle, and A5 has not yet confirmed that no dashboard action needs a mailbox key.
