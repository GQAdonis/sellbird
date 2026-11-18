# Design: Sellbird's generic manifests, migration job and the digest-pinning deploy bot targeting the platform repo

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 9). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Add infra/k8s base (Deployment with read-only root and non-root securityContext, ServiceAccount, Service, NetworkPolicy allowing only flint-gate, a migration Job running `sellbird storage migrate` with the migration-role Secret, app Secret references by name via secretKeyRef only, including `sellbird-claude`) and an overlays/example overlay using example.test values only. Add the deploy job: after images.yml outputs the digest, it mints a GitHub App token for the platform repository named by a repository variable (no literal), and writes newTag+digest into the overlay path defined by the platform contract, with SHA/digest regex, never-backwards, changed-lines-only and retry guards. Add infra/github/main-ruleset.json (required checks from tests.yml) and CODEOWNERS for this fork. No real hostname or registry literal appears in this repository; the production overlay and the Argo CD AppProject/Application live in the platform repository. Applying settings or anything to the cluster is operator-approved; live sync is gated on the platform phase.

### Manifests (tasks 9.1, 9.2)

`infra/k8s/base` (namespace `sellbird`, set by the base's `namespace:`; no Namespace object):

| File | Object | Notes |
|---|---|---|
| `serviceaccount.yaml` | ServiceAccount `sellbird` | `automountServiceAccountToken: false` (pods repeat it) |
| `service.yaml` | Service `sellbird`, ClusterIP, port `http` 5555 | selects `name: sellbird, component: app` |
| `networkpolicy.yaml` | `sellbird-default-deny`, `sellbird-app-ingress-from-flint-gate`, `sellbird-egress-dns-and-postgres`, `sellbird-app-egress` | exactly the contract table; one peer with both namespace and pod selectors (AND); internet egress `0.0.0.0/0` except 10/8, 172.16/12, 192.168/16, 100.64/10, 169.254/16, 127/8 on TCP 80, 443, 465, 587, 993 |
| `migrate-job.yaml` | Job `sellbird-migrate` | `argocd.argoproj.io/hook: PreSync`, `hook-delete-policy: BeforeHookCreation`, `sync-wave: "-1"`; args `storage migrate`; `SELLBIRD_MIGRATE_DATABASE_URL` from `sellbird-db-migrate`/`SELLBIRD_DATABASE_URL` (the migrate CLI prefers it); `backoffLimit: 1`, `activeDeadlineSeconds: 900`; `/data`, `/tmp` emptyDirs |
| `deployment.yaml` | Deployment `sellbird` | one replica, `Recreate`, `sync-wave: "0"`; args `dashboard --host 0.0.0.0 --port 5555`; `envFrom` ConfigMap `sellbird-gateway` (required); `SELLBIRD_DATABASE_URL` from `sellbird-db-app`, `CLAUDE_CODE_OAUTH_TOKEN` from `sellbird-claude`; tcpSocket startup/readiness/liveness probes on 5555; `/data` (1Gi), `/tmp` (2Gi) and `/dev/shm` (Memory, 256Mi) emptyDirs; requests 250m/512Mi, memory limit 2Gi |

Both workloads: pod `runAsNonRoot`, uid/gid/fsGroup 1000, seccomp `RuntimeDefault`, `enableServiceLinks: false`; container `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, drop `ALL`. The image is the logical name `sellbird`; overlays pin it.

`/data` is an emptyDir, not a PVC: the contract's AppProject whitelist has no PersistentVolumeClaim, and state is in Postgres. Settings saved from the dashboard into `/data` are lost on restart; a PVC needs a contract change.

`infra/k8s/overlays/example`: the base, ConfigMap `sellbird-gateway` with the contract's placeholder values, and an `images` entry `name: sellbird`, `newName: ghcr.io/example-owner/sellbird`, a shape-valid placeholder `newTag` and `digest`, in the fixed line order the bot relies on.

Not in the base: `sellbird-providers` keys (the contract allows them as optional keys; the platform overlay adds the ones the operator uses with a patch), and any cluster-specific egress `except` range.

### Deploy job (task 9.3)

Job `deploy` ("pin production overlay") in `.github/workflows/images.yml`: `needs: images`, `if: github.ref == 'refs/heads/main'`, `environment: production`, `permissions: contents: read`, concurrency `deploy-production` (never cancelled). Steps:

1. Configuration check: variable `SELLBIRD_DEPLOY_APP_CLIENT_ID`, environment secret `SELLBIRD_DEPLOY_APP_PRIVATE_KEY` (tested as `!= ''`, never printed), variable `SELLBIRD_PLATFORM_REPO` matching `<owner>/<repo>`; any missing item fails the job before a token exists, so nothing is pushed. It also re-validates the `images` outputs (tag equals `github.sha`, digest and image regexes).
2. Check out this repository at `github.sha` with full history (`persist-credentials: false`) for the ancestry check.
3. `actions/create-github-app-token` (v3.3.0, `64ab729a6294000f5aa4a4bc0b73d1f32bc45510`, inputs read from its `action.yml`: `client-id`, `private-key`, `owner`, `repositories`, `permission-contents`) scoped to the platform repository, Contents write.
4. Check out the platform repository's `main` with that token; author commits as `<app-slug>[bot]`.
5. `scripts/deploy/pin_overlay.sh`, then push to `main`; on rejection fetch, `reset --hard origin/main`, pin again (up to 4 attempts).

`scripts/deploy/pin_overlay.sh` (pure over two checkouts and the inputs; never pushes): validates tag `^[0-9a-f]{40}$`, digest `^sha256:[0-9a-f]{64}$` and image name first; requires a clean overlay checkout, exactly one `  - name: sellbird` line and exactly one `newTag` and one `digest` line in the file, in the fixed order name, newName, newTag, digest (a tag-only entry is refused); refuses unless the pinned SHA is a strict ancestor of the new SHA in this repository (same SHA and digest exits 3, a no-op); rewrites in a temporary file, checks that exactly two lines are removed and two added, all of them newTag/digest lines, each new line exactly once; installs, re-checks with `git diff --name-only`/`--numstat`, and commits `chore(sellbird): pin <sha> <digest>`. Any refusal restores the file, so the checkout is unchanged. Exit codes: 0 pinned, 3 nothing to do, 1 refused, 2 usage.

A backwards pin fails the job (red) instead of exiting quietly, so an out-of-order run is visible. The first pin in the platform overlay must be a real commit of this repository's `main` (placeholders are refused); the runbook's bootstrap step covers it.

### Ruleset, CODEOWNERS, runbook (task 9.4)

`infra/github/main-ruleset.json`: `deletion`, `non_fast_forward`, `pull_request` (1 approval, code-owner review, dismiss stale), `required_status_checks` with the seven `tests` names from image-build-scan-publish's "Required checks" (`integration_id` 15368); bypass `RepositoryRole` 5 (admin) with `pull_request`. No `images.yml` check is required: that workflow never runs on `pull_request`, so requiring `build and scan`, `publish to GHCR` or `pin production overlay` would block every pull request.

The deploy App pushes only to the platform repository, so its `Integration` bypass (`always`) goes into the platform repository's ruleset, not this one; `infra/github/README.md` gives that command and the order: App, key, environment and variables, platform bootstrap pin, platform bypass, CODEOWNERS substitution, then this ruleset after `tests` is green on `main` and the deploy job is merged. `.github/CODEOWNERS` covers `/infra/`, `/.github/`, `/scripts/deploy/` and `/Dockerfile` with the placeholder `@REPLACE_WITH_OWNER`.

### Boundary check (task 9.5)

`scripts/boundary/check_manifests.sh <overlay>` (not run before the boundary): renders with `sb_kustomize` from `preflight.sh`, converts to JSON with `sb_yq_stdin`, asserts the items in its header (pinning, default deny and flint-gate-only ingress, container and pod security, PreSync Job with only `sellbird-db-migrate`, secretKeyRef-only secrets, AppProject kinds only, no Namespace, no non-placeholder hostname or email in the render or `infra/k8s` sources), then runs `pin_overlay.sh` against scratch repositories: forward pin accepted with exactly the two lines changed and the expected commit message; no-op, same-tag-new-digest, tag-only (no digest, empty digest, tag-only entry), backwards, diverged, malformed digests and tag, unknown commit, wrong image, wrong line order, a second pin pair, a dirty checkout and a placeholder current pin all refused with the repository unchanged.

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

Changed baseline test files (justified): none yet.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.
- Not executed before the boundary (VLBV): kustomize, yq, actionlint, the workflow and both scripts. Boundary evidence: `scripts/boundary/check_manifests.sh infra/k8s/overlays/example` exit 0; actionlint on `images.yml`; the first real deploy run (configuration check, App-authored pin commit in the platform repository passing its ruleset).
- DNS egress selects `k8s-app: kube-dns` in `kube-system`. With GKE NodeLocal DNSCache (a link-local address) DNS would be blocked; the platform overlay would need an egress patch.
- Cluster pod or service ranges outside the `except` list would be reachable on the internet ports; the platform overlay adds them.
- Admin bypass with `pull_request` skips status checks too; with one maintainer as sole code owner every owned-path merge is a bypass. The App key can rewrite the platform repository's `main`; the main-only environment limits who can read it, not what it can do.
- `@REPLACE_WITH_OWNER` makes CODEOWNERS invalid until substituted; applying the ruleset first would block owned-path pull requests for non-bypass writers.

## Open Questions

None that change what gets built; the platform contract's operator agreement is tracked as a boundary receipt.
