# GitHub settings for the delivery path: operator runbook

This folder holds the settings that the deploy path needs but that live in
GitHub, not in files GitHub reads on its own: the branch ruleset for this
repository (`main-ruleset.json`) and the steps to create the deploy App, the
`production` environment, its variables and its secret.

Every step here changes a setting outside this repository. Each one is the
operator's action, approved one at a time. Nothing in this folder is applied by
CI or by an agent. Credentials are generated and stored by the operator only:
nobody else reads, prints, copies or stores the App's private key.

Placeholders used below (never replace them in this file; substitute them in
your shell):

| Placeholder | Meaning |
|---|---|
| `<owner>/sellbird` | this repository |
| `<platform-owner>/<platform-repo>` | the platform repository (contract: Actions variable `SELLBIRD_PLATFORM_REPO`, example value `example-org/platform`) |
| `<client-id>` | the deploy App's Client ID (not secret) |
| `<app-id>` | the deploy App's numeric App ID (not secret; needed for the platform ruleset bypass) |
| `<key-file>` | the exact file name of the downloaded private key |

## What the pipeline does

1. A merge to `main` runs `.github/workflows/images.yml`: job `build and scan`
   builds and scans, job `publish to GHCR` pushes `ghcr.io/<owner>/sellbird:<sha>`
   and outputs the digest.
2. Job `pin production overlay` (environment `production`, main only) mints a
   token for the deploy App, scoped to the platform repository with Contents
   write, and runs `scripts/deploy/pin_overlay.sh` against
   `apps/sellbird/overlays/production/kustomization.yaml` there. It pushes one
   commit, `chore(sellbird): pin <sha> <digest>`, that changes only the `newTag`
   and `digest` lines.
3. Argo CD (AppProject and Application owned by the platform repository) syncs
   that overlay: the PreSync migration Job, then the Deployment on
   `image:<sha>@sha256:<digest>`.

The bot never pushes to this repository. It pushes to the platform repository's
`main`, so the App's ruleset bypass belongs to the **platform** repository's
ruleset (step 5), not to `main-ruleset.json`.

## Order

1. Create the App and install it on the platform repository only.
2. Generate the private key; store it as an environment secret.
3. Create the `production` environment (main only) and the two variables.
4. Bootstrap the platform overlay with a real pin.
5. Platform repository: let the App push to its `main`.
6. Replace the CODEOWNERS placeholder (reviewed pull request here).
7. Apply `main-ruleset.json`, **only after** the `tests` checks are green on
   `main` and the deploy job is merged.

If the deploy job merges before steps 1 to 4 are done, its first step fails with
"deploy is not configured, nothing pushed": no token is minted, nothing is
written. After the configuration exists, re-run only that job:
`gh run rerun <run-id> --failed`.

## 1. Create the deploy App

In the browser, on the account that owns the platform repository, create a
GitHub App (Settings, Developer settings, GitHub Apps, New GitHub App):

- name: something like `sellbird-deployer`; homepage: this repository;
- webhook: **inactive**;
- repository permissions: **Contents: Read and write** (Metadata: Read-only is
  added automatically); nothing else, no account permissions, no events;
- where it can be installed: **Only on this account**.

Record the **Client ID** (`<client-id>`) and **App ID** (`<app-id>`). Neither is
secret. Install the App with **Only select repositories** and choose the platform
repository only. Check the installation afterwards:

```bash
gh api /user/installations --jq '.installations[] | {app_slug, repository_selection, permissions}'
```

Expected: `repository_selection: selected`, permissions `contents: write` and
`metadata: read` only.

## 2. Private key (operator only)

App settings, **Private keys**, **Generate a private key** (not "Client
secrets"). Store it only as a secret of the `production` environment, then
delete the downloaded file:

```bash
gh secret set SELLBIRD_DEPLOY_APP_PRIVATE_KEY --repo <owner>/sellbird --env production < ~/Downloads/<key-file> \
  && rm -P ~/Downloads/<key-file>
```

Use the literal file name, not a wildcard. Never store the key as a
repository-level secret: a repository secret is readable by workflows on any
branch, including pull requests. Check that no repository-level copy exists:

```bash
gh secret list --repo <owner>/sellbird            # must NOT list SELLBIRD_DEPLOY_APP_PRIVATE_KEY
gh secret list --repo <owner>/sellbird --env production
```

## 3. Environment and variables

```bash
R=repos/<owner>/sellbird
gh api -X PUT $R/environments/production --input - <<'JSON'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
JSON
gh api -X POST $R/environments/production/deployment-branch-policies -f name=main -f type=branch
gh variable set SELLBIRD_DEPLOY_APP_CLIENT_ID --repo <owner>/sellbird --env production --body '<client-id>'
gh variable set SELLBIRD_PLATFORM_REPO       --repo <owner>/sellbird --env production --body '<platform-owner>/<platform-repo>'
```

No required reviewers on the environment: they would stop continuous delivery.
The variables may also be repository-level; environment-level keeps everything
the deploy job needs behind the main-only policy.

## 4. Bootstrap the platform overlay

`pin_overlay.sh` refuses to move from a pin that is not a commit on this
repository's `main` (the never-backwards check needs a real ancestor). So the
platform repository's first `apps/sellbird/overlays/production/kustomization.yaml`
must carry a real pin, added by a reviewed pull request there:

- `newTag`: the SHA of a commit on this repository's `main` that `images`
  published (quoted, 40 hex);
- `digest`: that run's digest (job summary "Published", or artifact
  `image-digest-<sha>`, file `image-digest.env`);
- the `images` entry in the fixed line order `name`, `newName`, `newTag`,
  `digest`, exactly as in `infra/k8s/overlays/example/kustomization.yaml`, and no
  other `newTag` or `digest` line in that file;
- the remote base pinned to a commit SHA of this repository.

## 5. Platform repository: let the App push

The platform repository's own `main` ruleset must allow the App to push the pin
commit. That is a change in the platform repository, approved there:

```bash
gh api repos/<platform-owner>/<platform-repo>/rulesets --jq '.[] | {id, name}'
gh api repos/<platform-owner>/<platform-repo>/rulesets/<id> \
  | jq --argjson id <app-id> '{name, target, enforcement, conditions, rules,
        bypass_actors: (.bypass_actors + [{actor_id: $id, actor_type: "Integration", bypass_mode: "always"}])}' \
  | gh api -X PUT repos/<platform-owner>/<platform-repo>/rulesets/<id> --input -
```

`bypass_mode: always` lets the App push (and force-push) to that `main`. That is
why its key lives only in the main-only `production` environment.

The App is not installed on this repository and needs no bypass in
`main-ruleset.json`. If a later change ever makes the bot push here, add it the
same way at apply time
(`.bypass_actors += [{actor_id: <app-id>, actor_type: "Integration", bypass_mode: "always"}]`)
and record the difference between the file and the live ruleset.

## 6. CODEOWNERS

`.github/CODEOWNERS` names `@REPLACE_WITH_OWNER`. Replace it with the real owner
handle (a user, or `@org/team` with write access) in a pull request in this
repository. Do it before step 7: with the placeholder in place no code-owner
review can be satisfied, so every pull request touching `/infra/`, `/.github/`,
`/scripts/deploy/` or `Dockerfile` would need an owner bypass.

## 7. Apply the ruleset

Preconditions, checked just before applying:

```bash
gh api repos/<owner>/sellbird/commits/main/check-runs \
  --jq '.check_runs[] | "\(.app.id) \(.conclusion) \(.name)"'
```

Every required check below must appear with app id `15368` (GitHub Actions) and
`success`. A required check that is red on `main` blocks every pull request for
everyone except bypass actors. If the names differ (for example the matrix
changed), correct the file in a pull request first.

| Required check (`context`) | From |
|---|---|
| `test (ubuntu-latest, 3.11)` | `tests.yml` job `test` |
| `test (ubuntu-latest, 3.12)` | `tests.yml` job `test` |
| `test (macos-latest, 3.11)` | `tests.yml` job `test` |
| `test (macos-latest, 3.12)` | `tests.yml` job `test` |
| `test (windows-latest, 3.11)` | `tests.yml` job `test` |
| `test (windows-latest, 3.12)` | `tests.yml` job `test` |
| `postgres` | `tests.yml` job `postgres` |

`images.yml` (`build and scan`, `publish to GHCR`, `pin production overlay`)
runs only on pushes to `main` and manual runs, never on pull requests, so none
of its jobs can be a required pull-request check: requiring one would block
every pull request forever.

Apply (first time), then verify:

```bash
gh api -X POST repos/<owner>/sellbird/rulesets --input infra/github/main-ruleset.json
gh api repos/<owner>/sellbird/rules/branches/main --jq '[.[].type]'
# expected: ["deletion","non_fast_forward","pull_request","required_status_checks"]
```

Later changes: `gh api -X PUT repos/<owner>/sellbird/rulesets/<id> --input infra/github/main-ruleset.json`.

The ruleset:

- forbids deleting or force-pushing `main`;
- requires a pull request with one approving review, including a code owner's
  for owned paths, and dismisses stale approvals on new pushes;
- requires the seven `tests` checks;
- lets the repository **admin** role (`RepositoryRole` id 5; on a personal
  repository that is the owner) merge pull requests past those rules
  (`bypass_mode: pull_request`), but not push to `main` directly. For an
  organization-owned repository, `{"actor_id": 1, "actor_type":
  "OrganizationAdmin", "bypass_mode": "pull_request"}` is the equivalent.

## Risks to state plainly

- An admin's `pull_request` bypass skips status checks too, not only review.
  With a single maintainer who is also the only code owner, every change to an
  owned path merges by bypass; the ruleset binds other writers.
- The App's key can rewrite the platform repository's `main` (bypass
  `always`). The main-only environment keeps it away from branch and pull
  request workflows; it does not make the key less powerful. Rotate it by
  generating a new key, replacing the environment secret, then deleting the old
  key in the App settings.
- Whoever can merge to this repository's `main` controls what the deploy job
  runs, including `scripts/deploy/pin_overlay.sh`. CODEOWNERS covers those
  paths; the admin bypass does not.
- A backwards pin is refused and the job fails red rather than silently
  skipping, so an out-of-order run is visible.
