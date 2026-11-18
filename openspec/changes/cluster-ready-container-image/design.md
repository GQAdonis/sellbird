# Design: Make the Sellbird image reproducible and runnable in Kubernetes

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 6). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Pin the Claude CLI to an exact version with checksum verification instead of an unpinned install script, move writable state to a /data volume so the root filesystem can be read-only, run gateway mode by configuration with a health endpoint reachable from the Service, keep the non-root user, include the Postgres client dependencies, and never log the token. The brain reads CLAUDE_CODE_OAUTH_TOKEN from the environment only (Secret `sellbird-claude`), with no credential written under /data or /home.

### Claude CLI pin (task 6.1)

- Version **2.1.311**, the `stable` channel value of `https://downloads.claude.ai/claude-code-releases/stable` on 2026-11-18 (`latest` was 2.1.327).
- Install method: the native binary that the documented installer itself downloads (`<releases>/<version>/<platform>/claude`, https://code.claude.com/docs/en/setup, "Binary integrity and code signing"). The installer script is no longer run, so there is no unpinned script, no launcher written to `$HOME` and no auto-updater.
- Checksums: `platforms.<platform>.checksum` from `https://downloads.claude.ai/claude-code-releases/2.1.311/manifest.json`. Its detached signature `manifest.json.sig` verified ("Good signature", key `31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE`, Anthropic Claude Code Release Signing) when the pin was recorded.
  - `linux-x64`: `86dc1fcc69498159eaf15f446613e847010f9036bfbbdffd4c49350be8489ada`
  - `linux-arm64`: `2e2496c9a8065df93acb0fca2d341f59a6b8777649b2e025ab8c9bcd5eef61f3`
- Build-time enforcement (Dockerfile stage `claude-cli`): `sha256sum -c` against the pinned value (a mismatch fails the build: the spec's "tampered installer" scenario), then the manifest's GPG signature must be a `VALIDSIG` by the pinned fingerprint and the signed manifest must name the pinned version and list the same checksum. The runtime stage then requires `claude --version` to start with the pinned version and runs `sellbird.claude_runtime.check_cli()` (unchanged) with a throwaway config directory.
- Bumping: change `CLAUDE_CODE_VERSION` and both checksums together, from the new release's signed manifest.
- Base image: `python:3.12.16-slim-trixie` pinned by its multi-arch index digest `sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b` (Docker Hub, updated 2026-11-08). The previous Dockerfile used the floating `python:3.12-slim`, which pointed at the same digest.

### Writable state and runtime contract (task 6.2)

No Python changes were needed. `sellbird.paths` already honours `SELLBIRD_HOME` and `sellbird.home.seed_home` already copies missing defaults from `<sys.prefix>/share/sellbird` into the home before every command, so:

| Item | Value |
|---|---|
| `SELLBIRD_HOME` | `/data` (declared `VOLUME`, owned by the runtime user, mode 0700). Config is seeded to `/data/sellbird.yaml`, `/data/prompts`, `/data/skills`; state is `/data/data/` (SQLite file, dashboard token in local mode, pid/lock files). In the cluster the database is Postgres (`SELLBIRD_DATABASE_URL`). |
| Shipped defaults | `/usr/local/share/sellbird` (what `home.bundled_defaults()` finds, since `/app` is not a checkout). |
| Code | `/app` (root-owned, not writable by the runtime user). `migrations/` is at `/app/migrations`; `SELLBIRD_MIGRATIONS_DIR=/app/migrations/postgres` is set explicitly. |
| `/tmp` | must be a writable tmpfs/emptyDir: Python temp dirs, the per-call Claude working directory, Chromium, and the Claude CLI config directory. |
| `CLAUDE_CONFIG_DIR` | `/tmp/claude`: whatever the CLI writes (settings cache, not credentials) is in memory and gone on restart; nothing under `/data` or `$HOME`. `DISABLE_AUTOUPDATER=1`, `DISABLE_UPDATES=1`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`. |
| AI credential | `CLAUDE_CODE_OAUTH_TOKEN` from the environment only. `claude_runtime.runtime_env` passes the parent environment through unchanged apart from its stripped list, so the CLI receives it. No credentials file exists in the image, `$HOME` or `CLAUDE_CONFIG_DIR`, so with the variable unset there is nothing to fall back to. |
| `SELLBIRD_CONTAINER` | `1` (requested by hosted-gateway-mode): local mode prints no unlock link and `dashboard --url` is refused. |
| Mode | local by default; gateway only with `SELLBIRD_DASHBOARD_MODE=gateway`. The Deployment passes args `dashboard --host 0.0.0.0 --port 5555`; without the variable that `--host` is refused, so the args alone cannot open a non-loopback listener. |
| Health | `HEALTHCHECK` is a TCP connect to `127.0.0.1:$SELLBIRD_HEALTHCHECK_PORT` (default 5555), which works in both modes (gateway mode returns 400 to any request without the public `Host`). Kubernetes ignores it; probes must be `tcpSocket` on port 5555. |
| User | `sellbird`, uid/gid 1000 by default (build args, both must be > 0). |

Local Docker Compose keeps working by setting `SELLBIRD_HOME=/app`, `SELLBIRD_MIGRATIONS_DIR=/app/migrations/postgres` and `CLAUDE_CONFIG_DIR=/home/sellbird/.claude` (the host's mounted login). Since `SELLBIRD_CONTAINER=1`, the local unlock link is no longer printed in Compose logs; docs/docker.md shows how to build it from `data/dashboard-token`.

### Dependencies and labels (task 6.3)

- The `hosted` (`pyjwt[crypto]`) and `postgres` (`psycopg[binary]`) extras are read from `pyproject.toml` at build time (bind-mounted for that step only, so `/app` never looks like a checkout) and installed with `requirements.txt`; the build imports `jwt` and `psycopg` to prove it. `.dockerignore` admits `pyproject.toml` and `migrations/`.
- OCI labels: `org.opencontainers.image.{title,description,source,revision,version,licenses}` plus `dev.sellbird.claude-code.version`. CI passes `--build-arg VCS_REF=<sha>`, `SELLBIRD_VERSION`, `SOURCE_URL`; no `created` label, to keep builds reproducible.

### Boundary check (task 6.4)

`scripts/boundary/check_container.sh [--brain] <image>` (not run before the boundary). It runs the image with `--read-only`, `--tmpfs /tmp:rw,nosuid,nodev,exec`, `--cap-drop ALL`, `no-new-privileges`, a fresh named volume at `/data` and `--network none`, in local mode and gateway mode (placeholder `example.test` config), and checks the items listed in its header. `--brain` drives `sellbird.brain.Brain.think` itself: once with a stand-in `claude` that reports the SHA-256 of the token it received, once with the variable unset against the real pinned CLI.

### Notes for the manifests (change 9) and the gateway stand-in (change 7)

- Pod `securityContext`: `runAsNonRoot: true`, `runAsUser: 1000`, `runAsGroup: 1000`, `fsGroup: 1000`, `seccompProfile: RuntimeDefault`. Container: `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`.
- Volumes: `/data` (a PVC if settings saved from the dashboard, such as `sellbird.local.yaml`, must survive restarts; an emptyDir otherwise, since state is in Postgres); `/tmp` emptyDir (`medium: Memory` with a `sizeLimit`, or disk); optionally `/dev/shm` emptyDir `medium: Memory` for Chromium.
- App container args `["dashboard", "--host", "0.0.0.0", "--port", "5555"]`, env from ConfigMap `sellbird-gateway`, `CLAUDE_CODE_OAUTH_TOKEN` from `secretKeyRef` `sellbird-claude`. Probes `tcpSocket: {port: 5555}` (an `httpGet` probe gets 400 without the public `Host`).
- Migration Job: same image, args `["storage", "migrate"]`, same security context, `/tmp` and `/data` emptyDirs (every command seeds `/data` first; an unwritable `/data` only prints one stderr line). `SELLBIRD_MIGRATIONS_DIR` is already set in the image.
- The stand-in (change 7) can run the boundary image the same way: `--read-only --tmpfs /tmp:rw,exec -v <volume>:/data`, the gateway env, args `dashboard --host 0.0.0.0`, port 5555 published.
- Image size grows by the ~290 MB native CLI binary (it replaced the installer's copy, so the net change is small).

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

Changed baseline test files (justified): none yet.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.
- Missing-login wording: the brain recognises a logged-out CLI by stderr fragments (`not logged in`, `please run \`claude login\``, `invalid api key`, `unauthorized`). If CLI 2.1.311 reports a missing login only on stdout (for example inside the JSON result) the brain retries and returns "" without its documented "Non-retryable Claude error (auth)" line, and the `--brain` check fails. That would need a repair in `sellbird/brain.py` (backend owner), not in the image.
- `/tmp` exec: the check mounts `/tmp` with `exec`, matching a Kubernetes emptyDir. Whether the CLI or Chromium works with a `noexec` `/tmp` was not verified.
- Quota gauge: `sellbird.integrations.quota` reads only a credentials file or the keychain, so in the cluster (token in the environment only) the subscription-quota gauge is unavailable and the budget check falls back. It reads, never writes.
- BuildKit is required (`RUN --mount`); the legacy builder fails on it.
- The build needs network access to `downloads.claude.ai` (binary, manifest, signature, key).

## Open Questions

None that change what gets built; the platform contract's operator agreement is tracked as a boundary receipt.
