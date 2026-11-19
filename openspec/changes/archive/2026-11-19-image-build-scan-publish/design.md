# Design: Build, scan and publish the image to GHCR by digest on merge to main

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 8). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Add .github/workflows/images.yml following the github-argocd-continuous-deployment reference pattern: build with buildx, a non-root check, a vulnerability scan with a fail threshold on CRITICAL, an artifact secret scan with a planted-secret negative control that must fail, refuse to push if the SHA tag already exists, push `ghcr.io/<owner>/sellbird:<sha>` (owner = `github.repository_owner`, lowercased in the workflow; no account name is written literally), and expose the digest as a job output. paths-ignore the overlay so the bot's pin commit does not rebuild.

### Workflow shape (tasks 8.1, 8.2)

`.github/workflows/images.yml`, two jobs:

| Job | Token | Does |
|---|---|---|
| `build` ("build and scan") | `contents: read` only | checkout (no persisted credentials); compute the image name; Buildx build of `Dockerfile`, `linux/amd64`, `load: true`, no push, `provenance: false`, `sbom: false`, build args `VCS_REF=<sha>`, `SELLBIRD_VERSION=<pyproject version>`, `SOURCE_URL=<server>/<repository>`; non-root check; secret-scan negative control; secret scan; vulnerability scan; `docker save` of the scanned image as a one-day artifact |
| `images` ("publish to GHCR") | `packages: write` only | only when `github.ref == refs/heads/main`; download the artifact, check its SHA-256 and that the loaded image ID equals the scanned image ID; log in with `GITHUB_TOKEN`; refuse if `<image>:<sha>` exists; push the `<sha>` tag; read and confirm the digest; set outputs; upload `image-digest-<sha>` |

Splitting the jobs keeps third-party scanner code (trivy-action and the setup-trivy action it calls, which reads `github.token` by default) away from a token that can write packages. The cost is moving the image (about 1-2 GB uncompressed) between jobs as an artifact.

Triggers: `push` to `main` and `workflow_dispatch`. A manual run on a branch other than `main` builds and scans but never publishes. `concurrency: images-<sha>`, never cancelled, so two runs of one commit queue and the second is refused by the existing-tag check.

`paths-ignore` lists only paths that cannot change the image: root-level `*.md` (GitHub's `*` does not cross `/`, so `prompts/*.md` and `skills/*.md`, which are shipped in the image, still trigger), `docs/**`, `openspec/**`, `infra/**` (the Kustomize base and any pins; the production overlay itself is in the platform repository, so the bot's pin commit never lands here), `tests/**`, `harvey/**`, `scripts/boundary/**`, `scripts/diagnose_overpass.py`, agent and tool folders (`.kbd-orchestrator/**`, `.agent-team/**`, `.codex/**`, `.impeccable/**`, `.kimi-code/**`, `.opencode/**`, `.qwen/**`, `.claude/**`), issue/PR templates, `tests.yml`, `deploy.yml`, `docker-compose.yml`, `.env.example`, `.gitignore`, `LICENSE`, `NOTICE`. Everything in the `.dockerignore` allowlist, the workflow itself and `scripts/ci/**` triggers a build.

### Gates before publishing and their thresholds

| Gate | Fails the run when |
|---|---|
| Non-root | image config `User` is empty, `root` or `0` (user part before any `:`); or `id -u` inside the image (`--network none`) is not a positive integer; or the `org.opencontainers.image.revision` label is not the commit SHA |
| Secret scan | Trivy (`scanners: secret`, all severities, built-in rules) reports any finding in the image (`exit-code: 1`) |
| Vulnerability scan | Trivy (`scanners: vuln`, `vuln-type: os,library`) reports a `CRITICAL` vulnerability that has a fixed version (`ignore-unfixed: true`). Unfixed CRITICALs and anything HIGH or lower do not block; raising the bar (for example to fixable HIGH) is a one-line change once the boundary run shows the baseline |
| Existing tag | `docker buildx imagetools inspect <image>:<sha>` succeeds (the tag exists), or fails with anything other than not found / manifest unknown / name unknown (fail closed on auth or network errors) |
| Digest | the push output has no `digest: sha256:<64 hex>`, the registry does not serve `<image>@<digest>`, or the tag resolves to a different digest |

Scanner: `aquasecurity/trivy-action` v0.36.0 pinned by commit, with Trivy itself pinned to v0.70.0 through the action's `version` input (the action's own default, written explicitly). `TRIVY_IMAGE_SRC=docker` makes every scan read the image from the local engine and never fall back to a registry copy.

Secret-scan configuration: Trivy's built-in allow rules skip every `*.md` file, and Sellbird ships `prompts/` and `skills/` as Markdown under `/usr/local/share/sellbird`. The workflow writes a secret config (`disable-allow-rules: [markdown]`) to the runner's temp directory and passes it as `TRIVY_SECRET_CONFIG` to both the control and the real scan. The other built-in allow rules stay (notably `^usr/local/lib/python[\d.]+/`, so third-party site-packages are not secret-scanned, and paths containing `test` or `example`); Sellbird's own files are under `/app` and `/usr/local/share/sellbird`, which those rules do not cover.

### Secret-scan negative control

Before the real secret scan, the `build` job proves the scanner, with exactly the configuration the real scan uses, fails on an image that contains a secret:

1. Generate a random value in GitHub personal-access-token shape (`ghp_` + 36 hex characters) at run time. No secret-shaped literal is committed, and the value is not a credential; it is masked in the log.
2. Build a throwaway derivative of the just-built image (docker-driver builder, `--pull=false`, local tag `sellbird-secret-control:<sha>`, never pushed) that adds the value in two places Sellbird's own content lives: `/app/planted-control.env` and `/usr/local/share/sellbird/skills/zz-planted-control.md` (the second also proves the Markdown allow rule is off).
3. Scan it with `exit-code: 1` and a JSON report, `continue-on-error: true`.
4. Require all of: the scan step's outcome is `failure`; the report is non-empty; it holds a `github-pat` finding whose target ends in each planted path. Otherwise the job fails, so a scanner that silently finds nothing (wrong config, wrong image, broken rule) can never let an image through. The control image is deleted afterwards.

This is the spec scenario "Planted secret blocks publishing": the same scan that trips on the control is the one that gates the real image, and `images` depends on `build` succeeding.

### Outputs the deploy job (change 9) can rely on

Job `images` outputs, set only after every gate above passed and the push was confirmed:

| Output | Format | Meaning |
|---|---|---|
| `tag` | `^[0-9a-f]{40}$` | the commit SHA the image was built from (= `github.sha`); the only tag pushed |
| `digest` | `^sha256:[0-9a-f]{64}$` | the manifest digest of `<image>:<tag>` as served by GHCR |
| `image` | `ghcr.io/<owner>/sellbird` | lowercased repository-owner image name (the overlay's `newName`) |

A deploy job in the same workflow uses `needs: images` and `needs.images.outputs.{tag,digest}`. A deploy workflow in a separate file cannot read job outputs; it can download the artifact `image-digest-<sha>` (90 days), file `image-digest.env` with lines `IMAGE=…`, `TAG=…`, `DIGEST=…`, for example from a `workflow_run` trigger on `images` with `conclusion == success`. Either way it must re-validate both regexes before editing the overlay (docs/platform-interface.md, "Overlay location and pin format"). The image is single-platform (`linux/amd64`), so the digest is an image manifest, not an index.

### Pinned actions

| Action | Tag | Commit |
|---|---|---|
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `docker/setup-buildx-action` | v4.4.1 | `f87e5991a6d7451dcb8d9637bfbc97413f497069` |
| `docker/build-push-action` | v7.4.0 | `c3c9e263c25d99ce0380d002d59b67737d91b0dc` |
| `aquasecurity/trivy-action` | v0.36.0 (annotated tag object `a9c7b0f0…`) | `ed142fd0673e97e23eac54620cfb913e5ce36c25` |
| `actions/upload-artifact` | v7.0.2 | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` |
| `actions/download-artifact` | v8.0.2 | `9000827ccba6bdab643e8b6fd33ac0654aef8333` |

Resolved 2026-11-18 with read-only `gh api repos/<owner>/<repo>/git/ref/tags/<tag>`; trivy-action's inputs (`version`, `scanners`, `ignore-unfixed`, `exit-code`, `format`, `output`) and its nested pin of `aquasecurity/setup-trivy` (v0.2.6, `3fb12ec1…`) were read from its `action.yaml` at that commit. Trivy's `github-pat` rule (`ghp_[0-9a-zA-Z]{36}`, CRITICAL) and its built-in allow rules were read from the Trivy v0.70.0 source.

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

Changed baseline test files (justified): none yet.

Not executed before the boundary: the workflow, Docker, actionlint and Trivy were not run (VLBV). Boundary evidence for tasks 8.1 and 8.2: actionlint on `images.yml`; one real run on `main` showing the control step tripped (both planted paths found), the secret and vulnerability scans passing, the push, and `images` outputs matching the regexes; GHCR serving `<image>:<sha>@<digest>`; a second run of the same commit (`workflow_dispatch` on `main`) failing at "Refuse to overwrite an existing tag" with nothing pushed.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.
- First push: the existing-tag check accepts only a "not found / manifest unknown / name unknown" answer. If GHCR answers a lookup in a package that does not exist yet with `denied` or `unauthorized`, the very first run fails closed; the repair is to recognise that exact answer, not to drop the check.
- Package visibility and linkage: GHCR creates the package on first push as private and, with `GITHUB_TOKEN`, linked to this repository. The cluster's pull access (public package or an image pull secret) is an operator setting, outside this change.
- Secret-scan false positives: Sellbird's own files were grepped for common secret shapes and none were found, but Trivy's full rule set was not run. A finding in the real image blocks publishing; a genuine false positive is handled by a narrowly scoped allow rule (one path, one rule) in the generated secret config, recorded here, never by turning the scan off.
- Scanner supply chain: trivy-action and setup-trivy had tags rewritten to malicious commits in an earlier 2026 incident. The commit pin (from a release published after remediation) protects against tag moves but not against a bad commit having been pinned; Trivy downloads its vulnerability database at run time, so the vulnerability gate can also fail on a database download outage.
- Image transfer: the scanned image moves between jobs as a gzip `docker save` artifact; the publish job checks its SHA-256 and image ID, but a large artifact makes the run slower and can hit storage quotas (retention is one day).
- Tests are not a prerequisite inside this workflow: `tests.yml` is a separate workflow, so `main` is assumed green through required checks on pull requests. A push that bypasses review could publish an untested image (still scanned).
- Single platform: `linux/amd64` only, matching the assumed GKE node pool; arm64 nodes would need a multi-platform build and an index digest.
- Build network: the Dockerfile downloads the Claude CLI from `downloads.claude.ai` and verifies its checksum; an outage there fails the build, never publishes an unverified binary.

## Open Questions

None that change what gets built; the platform contract's operator agreement is tracked as a boundary receipt.

## Required checks

Exact check names for the branch ruleset (change 9), from `.github/workflows/tests.yml` (workflow `tests`):

- `test (ubuntu-latest, 3.11)`
- `test (ubuntu-latest, 3.12)`
- `test (macos-latest, 3.11)`
- `test (macos-latest, 3.12)`
- `test (windows-latest, 3.11)`
- `test (windows-latest, 3.12)`
- `postgres` (Postgres 18 service container; fails on any skipped Postgres test)

The image workflow (`images.yml`) adds its own required check names, listed by the platform engineer.
