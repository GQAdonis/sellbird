# Hosting Sellbird (Postgres and a gateway)

Most people never need this page. Sellbird's default is a single install on your
own machine: state in a SQLite file, the dashboard on `127.0.0.1`, and a private
token link to open it. That stays the default and nothing here changes it.

This page is for the other case: running Sellbird as an always-on service with its
state in Postgres, sign-in handled by a gateway in front of it, and deploys driven
from Git. It's written for the person operating that service.

## Local or hosted?

| | Local (default) | Hosted |
|---|---|---|
| State | `data/sellbird.db` (SQLite) | Postgres 18, one database per Sellbird |
| Dashboard | `127.0.0.1:5555`, token link | behind flint-gate on your hostname |
| Sign-in | the token in the link | your Kratos session (with a second factor), checked by the gateway |
| Runs as | you, on your machine | a container, non-root, read-only |
| Setup | `pip install -e .` | this page |

Pick hosted only when you want Sellbird running somewhere other than your own
machine. What Sellbird does (finding prospects, writing, sending, replies) is the
same either way.

The hosted design is recorded in
[ADR 0001](adr/0001-shared-platform-and-single-tenant-database.md): Sellbird shares
a platform (Postgres, Kratos, flint-gate) with other services, and each Sellbird is
single tenant, one workspace per database. The exact names, keys and claims both
sides rely on are in the [platform interface](platform-interface.md); this page
doesn't repeat them.

## Use Postgres instead of SQLite

Install the extra and point Sellbird at a database:

```bash
pip install 'sellbird[postgres]'
export SELLBIRD_DATABASE_URL='postgresql://sellbird_app:...@db.example.test:5432/sellbird?sslmode=require'
```

With `SELLBIRD_DATABASE_URL` set to a `postgresql://` string, every store
(companies, prospects, the Outbox, signals, usage) lives in Postgres. Unset,
Sellbird uses `data/sellbird.db` as always. The string carries a password: keep it
in a Secret or your shell, never in a file in Git. Sellbird doesn't print it.

The string is for the **runtime role**, `sellbird_app`. That role reads and writes
rows and nothing else. It can't create, alter or drop tables, and Sellbird refuses
to start if the database's schema version isn't the one its code expects. So run
the migrations first (below).

## Provision the database and run migrations

Two roles, kept apart on purpose:

- `sellbird_migrate` owns the schema. Only it changes tables.
- `sellbird_app` is what Sellbird runs as.

`infra/postgres/provision.sql` creates the database and both roles as the
[platform interface](platform-interface.md#database-provisioning) describes. On a
shared platform, the platform runs it once. On your own test server, run it as a
superuser and supply the two passwords yourself. More in
[infra/postgres/README.md](../infra/postgres/README.md).

Then apply the schema as the migration role:

```bash
export SELLBIRD_MIGRATE_DATABASE_URL='postgresql://sellbird_migrate:...@db.example.test:5432/sellbird?sslmode=require'
sellbird storage migrate     # apply pending migrations
sellbird storage status      # where the schema is, and how many are pending
```

`migrate` reads `SELLBIRD_MIGRATE_DATABASE_URL`, then falls back to
`SELLBIRD_DATABASE_URL` (the hosted migration Job passes the migration role's
string under the second name). `--dsn-env NAME` reads a different variable.

Migrations are numbered and reversible, in `migrations/postgres/`. Going back is a
deliberate operator action and never happens on its own:

```bash
sellbird storage down --to 4 --yes   # drops tables and their rows
```

## Move an existing `data/sellbird.db` to Postgres

If you've been running locally and want to bring your data along:

```bash
sellbird storage migrate                      # the target must be on the current schema
sellbird storage move --from data/sellbird.db --to-env SELLBIRD_DATABASE_URL
```

`--to-env` names the variable that holds the target's connection string; Sellbird
reads it from there and doesn't print it. Use the runtime role's string.

What the move promises:

- **Your SQLite file is never changed.** It's opened read-only and read from one
  snapshot.
- **The target must be empty.** If it already holds any Sellbird row, the move
  refuses and writes nothing. Move only into a freshly migrated database; nothing
  is merged.
- **All or nothing.** It runs in one Postgres transaction. Every table is copied,
  then read back and compared with the source (row counts and a checksum). Any
  difference rolls the whole move back.
- **Same schema on both sides.** The SQLite file must be on its newest schema and
  the target fully migrated. Otherwise it refuses before writing a row.
- Ids are kept, and the next row Postgres inserts follows the moved ones.

Stop Sellbird before moving so nothing writes to the SQLite file mid-copy. A
running Sellbird makes the move stop on a lock rather than hang.

## Gateway mode: sign-in handled in front of Sellbird

In hosted mode Sellbird doesn't do its own sign-in. A gateway does:

1. The browser reaches your hostname through the shared Gateway, which sends it to
   flint-gate (never straight to Sellbird).
2. flint-gate checks the Kratos session. Only a session that passed the second
   factor gets through.
3. flint-gate mints a short-lived token (RS256, five minutes at most, audience
   `sellbird`) and forwards the request with it as `Authorization: Bearer ...`.
4. Sellbird verifies the token against flint-gate's published signing keys (a JWKS
   at a URL it was configured with, never one named inside a token), checks the
   issuer, audience and expiry, and checks the subject is on its allowlist.

If any of that fails, Sellbird answers 401 with an empty body. Cookies,
`X-Forwarded-*` and any `x-flint-*` header are ignored, so a request that merely
*claims* to come from the gateway gets nothing without a valid token. The local
dashboard token and the MCP agent token aren't used in this mode, and the
dashboard token is never created or printed.

Gateway mode is chosen by configuration only (a request can't pick it), from
these environment variables:

| Variable | What it is |
|---|---|
| `SELLBIRD_DASHBOARD_MODE` | `gateway` for hosted. Unset or `local` is the default. Anything else is refused. |
| `SELLBIRD_PUBLIC_HOST` | The one hostname Sellbird answers to, e.g. `sellbird.example.test`. |
| `SELLBIRD_GATE_ISSUER` | The expected token issuer, compared exactly, e.g. `https://gate.example.test`. |
| `SELLBIRD_GATE_AUDIENCE` | The expected audience: `sellbird`. |
| `SELLBIRD_GATE_JWKS_URL` | Where flint-gate publishes its signing keys. |
| `SELLBIRD_GATE_ALLOWED_SUBS` | Comma-separated Kratos identity ids (UUIDs) allowed in. At least one, at most 16. |

None of these is a secret. A missing or malformed value stops startup rather than
weakening a check. Sellbird's route file for flint-gate is
[`infra/flint-gate/sellbird-routes.yaml`](../infra/flint-gate/sellbird-routes.yaml),
explained in [infra/flint-gate/README.md](../infra/flint-gate/README.md). The full
list of claims and what's checked is in the
[platform interface](platform-interface.md#minted-claims).

## The AI credential in a pod

In a container there's no `claude login`. The brain takes its credential from the
`CLAUDE_CODE_OAUTH_TOKEN` environment variable only. You create the token once on
your own machine with `claude setup-token` and keep it in a Kubernetes Secret
(`sellbird-claude`). It's read as an environment variable and is not written to
disk or logged.

With the variable unset there's no file to fall back to: Sellbird logs
"Non-retryable Claude error (auth)" and the work waits. Codex isn't used in the
cluster. Rotation is manual: make a new token, replace the Secret, restart the
Deployment. Whether a subscription login may be used this way on a server is yours
to check against the provider's terms.

## The container

One image serves both the local Docker setup in [docker.md](docker.md) and the
hosted deployment. Hosted, it runs:

- as a non-root user, with a **read-only** root filesystem and all capabilities
  dropped;
- with writable space only at `/data` (`SELLBIRD_HOME=/data`) and a tmpfs at
  `/tmp`;
- with the Claude CLI pinned to an exact version and verified by checksum.

`scripts/boundary/check_container.sh <image>` checks those claims against a built
image. In Kubernetes `/data` is an `emptyDir`, so anything saved there (such as
settings changed from the dashboard) doesn't survive a restart. The real state is
in Postgres.

## How a change reaches the cluster

```
merge to main -> image built and scanned -> pushed by digest -> overlay pinned -> Argo CD syncs
```

1. **Merge to `main`.** `.github/workflows/tests.yml` has already run on the pull
   request, including a `postgres` job against a real Postgres 18.
2. **Build and scan.** `.github/workflows/images.yml` builds the image and scans
   it. A secret scan (checked against a planted-secret control) and a vulnerability
   scan must pass, or nothing is published.
3. **Push by digest.** The image goes to GHCR tagged with the commit SHA (a tag is
   never overwritten), and the job records its digest.
4. **Pin the overlay.** The `pin production overlay` job runs
   `scripts/deploy/pin_overlay.sh` against the **platform repository**, which holds
   the production overlay. It changes only the image tag and digest lines, in one
   commit, and refuses to move backwards.
5. **Argo CD syncs.** A PreSync Job runs `sellbird storage migrate` as the
   migration role. If it fails, the sync fails and the running version stays. Then
   the Deployment rolls to the new image.

The production overlay (real hostname, issuer, allowed identities, image pin) lives
in the platform repository, not here. This repository keeps hostname-free base
manifests in `infra/k8s/base` and a placeholder example overlay in
`infra/k8s/overlays/example`, which is what CI renders.

### Secrets

Created by the operator by hand in the `sellbird` namespace, never committed, and
referenced from manifests by name only:

| Secret | Key | Used by |
|---|---|---|
| `sellbird-db-migrate` | `SELLBIRD_DATABASE_URL` | the migration Job only |
| `sellbird-db-app` | `SELLBIRD_DATABASE_URL` | the app only |
| `sellbird-claude` | `CLAUDE_CODE_OAUTH_TOKEN` | the app only |
| `sellbird-providers` | your email, verifier and discovery keys, as named in `.env.example` | the app only |

The migration Job never sees the app's Secrets, and the app never sees the
migration role's.

### One-time GitHub setup

The deploy path needs a few settings that live in GitHub rather than in files: the
branch ruleset for `main`, a deploy GitHub App that can push the pin to the
platform repository, and a `production` environment holding its key. Each is an
operator action, done one at a time. The steps, in order, are in
[infra/github/README.md](../infra/github/README.md); the ruleset itself is
`infra/github/main-ruleset.json`.

## Try it locally first

`infra/local/compose.yaml` runs a stand-in for the hosted stack on your machine:
Postgres 18, Ory Kratos, flint-gate with Sellbird's real route file, and Sellbird in
gateway mode. You need Docker with Compose v2, plus `openssl` and `python3`.

```bash
docker build -t sellbird:boundary .
scripts/local/make-env.sh                                    # fresh credentials, keys and test identities
docker compose -f infra/local/compose.yaml up -d --wait
```

`make-env.sh` writes throwaway credentials under `infra/local/` (uncommitted) and
creates two test identities at `example.test` addresses, one allowed and one not.
Postgres, flint-gate and Sellbird are published on `127.0.0.1` only. Tear it down
with:

```bash
docker compose -f infra/local/compose.yaml down -v
```

`scripts/local/dsn.sh migrate|app` prints a connection string for the local
Postgres. Use it only in command substitution, since it contains a password; that's
how the storage tests run against it.
