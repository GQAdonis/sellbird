# Assessment — sellbird-go-live

Assessed 2026-11-22 against `origin/main` at `a661932` and the live host. Status: **complete**; both operator decisions are recorded under "Decisions".

## What the seeded goals asked for, and where each stands

The seed in `goals.md` came from the `postgres-gke-deployment` reflection, written before anything was pushed. Most of it has since been delivered.

| Seeded item | State | Evidence |
|---|---|---|
| Platform repo: Gateway, flint-forge PG18, Kratos with MFA, flint-gate, production overlay | Delivered by the platform phase | The platform session reports `shared-platform` CLOSED, PASS, 18 of 18. Not re-checked here. |
| Platform provisioning matches `docs/platform-interface.md`, including Sellbird's database and roles | Reported done, not re-checked | The platform session reports its database and shipping scenarios passed and the schema at version 5. This phase must not assume more of the interface than it re-checks. |
| History cleanup, push, open a PR | Done | PRs 1–5 are merged on `GQAdonis/sellbird`. |
| First runs of the CI matrix and the Postgres job | Done | On `a661932` the `tests` run passed all seven jobs: `postgres`, plus Ubuntu, macOS and Windows on Python 3.11 and 3.12. |
| First run of `images.yml` | Done | `images` succeeded on `a661932`. The two earlier failures were in the "pin production overlay" job only (deploy App configuration, then the platform checkout); build, scan and publish passed each time. |
| The Trivy control | **Not done** | No deliberate failing scan has ever been run, so nothing shows the scan step blocks a bad image. It was NOT_EXERCISED in the last phase and is added to the proposed scope below. |
| GitHub App deploy bot and protected-main ruleset | Done | The "pin production overlay" job succeeded on `a661932`; ruleset `main` is active. |
| Argo CD syncs Sellbird by digest | Reported done | Platform session: gate G11, Deployment Available on the pinned digest. Not re-checked here. |
| Host resolves, serves TLS, requires a session | Done for signed-out requests | `GET /`, `/api/status` and `/healthz` each return 401 over valid TLS with no session. |
| Signed-in dashboard loads | Reported done | Platform scenario SCN-AUTH-001 passed after the fix in PR 5. Not re-checked here. |
| F1: `exists()` raising for a missing database | Appears fixed | `storage_postgres/__init__.py` returns False for `3D000` and `42P01`; `tests/storage_contract/test_pg_failures.py` covers reachable and unreachable servers. The connect-time case with no SQLSTATE is not confirmed. |
| F2: CHANGELOG entry for stricter `exists()` and value-free errors | Open | No matching CHANGELOG line. |
| F3: stand-in host ports | Partly open | Postgres and the direct port are configurable; flint-gate's `4456` is fixed. |
| JWKS address must be https outside loopback | Open | `auth/config.py` `_jwks_url` accepts any `http://` host. The cluster uses an in-cluster `http://` address, so a strict rule needs an in-cluster exception. |
| NodeLocal DNS policy | Open, impact unknown | `networkpolicy.yaml` allows DNS to `kube-dns` pods only. Whether the cluster runs NodeLocal DNSCache is UNKNOWN; the app resolves Postgres today, which suggests it does not. |

## Gaps found now

0. **A stated precondition was not met.** The seeded goals said to clear F1–F3, the JWKS https rule and the NodeLocal DNS policy "before the first sync". The first sync happened during the platform phase with F2, F3, the JWKS rule and the DNS policy still open. No waiver is recorded. The sync has worked so far, so this assessment treats the four items as remediation in this phase, not as a reason to roll back. The operator can overrule that at plan review.

1. **The hosted pod only serves the dashboard.** `infra/k8s/base/deployment.yaml` runs `sellbird dashboard`. Nothing in the cluster runs the heartbeat (`sellbird run`), so the hosted Sellbird never prospects, writes, sends or reads replies. Whether "go-live" includes that is decision 1.
2. **Fresh install deadlocks.** The PreSync migration Job runs as ServiceAccount `sellbird`, which only the regular sync creates. It worked this time because the account already existed. (Raised by the platform session.)
3. **Signed-out visitors get a bare 401.** flint-gate has no redirect-to-login setting; a fix is in progress in the flint-gate repo. Sellbird's part is nil unless the platform chooses a Sellbird-side landing page.
4. **Hosted Sellbird is unconfigured.** No product training, no mail provider, no verifier key, no confirmed signals in the hosted database. UNKNOWN whether the Claude token secret (`sellbird-claude`) holds a working login.
5. **Open security findings** from `.agent-team/findings/security/postgres-gke-deployment-2829583.md`, all MEDIUM:
   - SEC-02: the parent-domain Kratos cookie is forwarded upstream, so a co-hosted app could replay it. Platform-side fix.
   - SEC-03, in three parts:
     - deploys are not gated on green tests: `.github/workflows/images.yml` in this repo;
     - persisted credentials: `images.yml` in this repo. Two checkouts already set `persist-credentials: false`; whether any remains is to be confirmed in the plan;
     - the deploy App can write the whole platform repo and bypass its rules: the App's permissions and the platform repo's ruleset, so a platform-side change.
   - SEC-04: the image ID is recorded after third-party scans run with Docker access; the Trivy binary is not checksummed.
   - SEC-05: dependencies install from ranges without hashes while merges auto-deploy.
   - LOW and not proposed: SEC-06 (aal check, kept by operator decision), SEC-07 (actions pinned by tag).
6. **Uncommitted local state.** `.kbd-orchestrator/*`, `CLAUDE.md`, `.agent-team/*`, `uv.lock` and others are modified or untracked on the working branch. Whether any belongs in the public repo is the operator's call.
7. **Process defect.** The `karpathy-progress-phase-boundary` hook fails (it calls `python3` where the script requires `uv run python`). It is a skill-pack defect, not Sellbird's.

## Recalled lessons that apply

- "External integrations require at least one real-service test": each scenario this phase adopts must run against the live host or the real pipeline, not the local stand-in.
- "Boundary gates must launch the packaged artifact": verification uses the published image as deployed, by digest.
- "Ask once at phase boundary for operator-only actions": merges, secrets and sign-ins are collected in one request at dispatch.
- "Discover test environment state instead of encoding checkout assumptions": the last phase lost four boundary attempts to host-port and environment assumptions; F3 exists for that reason.
- From the last reflection: 9 boundary attempts against a budget of 3, and 7 contract amendments. This phase should adopt a small contract with oracles checked before adoption.

## Knowledge gaps carried from prior context

G3, G4, G5 PARTIAL and G6 NOT MET in the last phase are now delivered or reported delivered (table above). The Trivy control is still unexercised and is in the proposed scope. `/learn-goal` is available for any of these on request.

## Adopted-outcome inputs

| Input | Value |
|---|---|
| Decision owner | The operator (sole approver, code owner) |
| User operation | The operator signs in at the id host with password and TOTP and uses the hosted dashboard |
| Observed baseline | Signed-out: 401 on every path. Signed-in dashboard: reported working, not re-checked. Heartbeat: not running in the cluster. Hosted configuration: none known. |
| Desired observable result | The hosted Sellbird completes heartbeat cycles in the cluster against the live database; the signed-in operator sees its activity on the dashboard; drafted emails wait in the Outbox and none is sent without approval |
| Supported environment | GKE cluster `main`, `us-south1`; one replica; cost ceiling $600 a month for the cluster |
| Required safety checks | Approval mode stays on (autopilot off); daily send limit and quiet hours; no real names or addresses in the repo; secrets never read or printed by agents; operator merges every PR |
| Exclusions | Tailscale; backups, high availability and autoscaling (earlier operator decision D12: Sellbird runs one replica without them); SEC-06; platform-repo changes (requested through that repo, not made here) |
| Risk acceptance | SEC-02 remains open until the platform fixes it; SEC-06 and SEC-07 are not addressed. Still UNKNOWN: which mailbox and verifier the hosted Sellbird uses, and which product it is trained on |

## Decisions

Answered by the operator on 2026-11-22, in this session's question dialog.

1. **What "live" means: Operating.** Run the heartbeat in the cluster and configure the hosted Sellbird (product, mailbox, verifier, signals), with every email held for approval. The remediation items in gap 0 (F2, F3, the JWKS rule, the DNS policy), gap 2 and the Trivy control are also in scope. Gaps 3, 6 and 7 are not.
2. **Security findings in scope: SEC-03, SEC-04 and SEC-05, all three.** SEC-02 stays with the platform. The part of SEC-03 that narrows what the deploy bot may push needs a change in the platform repo and is requested there, not made here.

## Proposed scope (for the plan and contract; not yet adopted)

- Migration Job no longer depends on a ServiceAccount the same sync creates.
- JWKS address rule: https required unless the host is loopback or an in-cluster service name.
- DNS egress policy that also works with NodeLocal DNSCache.
- F1: confirm `exists()` returns False for a missing database when the error arrives at connect time with no SQLSTATE, and fix it if not.
- F2 CHANGELOG entry; F3 configurable flint-gate port.
- SEC-03, this repo: gate the deploy job on green tests and remove any persisted credentials in `images.yml`.
- SEC-03, requested from the platform (not changed here): narrow what the deploy App may push and remove its rule bypass.
- SEC-04 and SEC-05, both in this repo.
- Run the Trivy control: a deliberate failing scan through the real pipeline, shown to stop publication.
- A heartbeat workload in `infra/k8s/base`, a documented way to load product configuration and provider secrets in hosted mode, and a first cycle observed against the live database with sending held in the Outbox.

## Open questions for analyze and plan

- Which product, mailbox provider and verifier the hosted Sellbird uses. These are operator inputs and secrets; agents never read them.
- How hosted mode receives product configuration. Sellbird reads `sellbird.yaml`, and `sellbird.local.yaml` wins when present (`sellbird/config.py` `load_config`; the dashboard writes the offer to the local file in `sellbird/dashboard.py`). Both are files on disk, and the pod's home is seeded from the image on each start, so anything written there is lost on restart. Which code path training itself writes through is to be traced in analyze.
- Whether the heartbeat is a second container, a second Deployment or the same process, given one replica and one writer.
- Whether `sellbird-claude` holds a working login, and how the Claude quota gauge behaves in a pod.
- Whether the cluster runs NodeLocal DNSCache.

## Review record

Independent review by `mimo-v2.6-pro` through the local gateway (producer `claude-fable-5-2`; the tool recorded the cross-model check as `unverified-producer-unknown` because the producer has no canonical identity tuple).

- Round 1: BLOCK. One CRITICAL (the Trivy control was marked done) and three WARNINGs (no evidence for the Postgres job, the "before the first sync" precondition, SEC-03 repo attribution). All four were corrected above.
- Round 2: PASS. Four WARNINGs (F1's connect-time case dropped from scope, an undefined "open follow-ups", an unsupported claim about where training writes configuration, platform-interface conformance not assessed). All four were corrected above; the corrections were not re-reviewed.
