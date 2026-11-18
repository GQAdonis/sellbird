# Sellbird platform interface contract

This document is the interface between Sellbird (this repository) and the shared
platform repository that runs the services Sellbird depends on in a hosted
deployment: the flint-forge Postgres 18 instance, Ory Kratos, flint-gate and the
shared Envoy Gateway. It says what each side provides, owns and may assume, so
the two repositories can be built and verified independently.

It covers hosted mode only. A local install (SQLite, loopback dashboard, token
link) needs none of this and does not change.

This repository is public. Every hostname, owner, repository name and identity id
below is a placeholder (see [Placeholders](#placeholders)). The real values live
only in the platform repository, which may be private.

The words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119.

## Status and agreement

- Contract version: `1`
- Status: proposed. It is agreed only when the operator records an agreement
  decision in the KBD decision log for phase `postgres-gke-deployment`. Editing
  this file, merging it, or a passing contract check does not agree it.
- The counterparty is the shared platform repository and its own KBD phase. That
  phase verifies its side against this document; this repository verifies its side
  with `scripts/boundary/check_platform_contract.sh docs/platform-interface.md`.
- Any change to a name, key, claim, path or format below bumps the contract version
  and needs a new agreement decision. Additive, optional fields need a version bump
  but not a change on the other side.
- Rationale for the overall split: `docs/adr/0001-shared-platform-and-single-tenant-database.md`.

## Ownership summary

| Concern | Owner | Sellbird's side |
|---|---|---|
| Postgres 18 server (flint-forge image), its superuser and backups | platform | none |
| `sellbird` database, its two roles and their grants | platform creates them once; Sellbird's migrations own the schema inside | runs migrations as the migration role, runs the app as the runtime role |
| Kratos (config, identity schema, admin API, login UI) | platform | none |
| The operator's Kratos identity | operator, through the platform's Kratos admin API | lists its id in the allowlist |
| flint-gate (issuer, signing keys, JWKS, `kratos_session` provider) | platform | verifies the tokens flint-gate mints |
| Sellbird's flint-gate site and routes | Sellbird (`infra/flint-gate/sellbird-routes.yaml`) | authored here with placeholder domains; the platform applies it |
| Gateway listener, hostname, TLS certificate, DNS record | platform | none |
| Sellbird's Kubernetes base manifests and migration Job | Sellbird (`infra/k8s/base`) | authored here, hostname-free |
| Production overlay, real hostname, image pins | platform (`apps/sellbird/overlays/production`) | the deploy bot writes the image pin only |
| Argo CD AppProject and Application for Sellbird | platform | none |
| Secrets in the `sellbird` namespace | operator, by hand | references them by name only |

## Namespaces

| Namespace | Holds | Owner |
|---|---|---|
| `sellbird` | Sellbird's Deployment, Service, ServiceAccount, ConfigMap, NetworkPolicy, migration Job and Secrets | platform creates the namespace; Argo CD syncs Sellbird's resources into it |
| `flint-gate` | flint-gate (pods labelled `app.kubernetes.io/name: flint-gate`, proxy port `4456`) | platform |
| `ory` | Kratos | platform |
| `flint-forge` | the shared Postgres 18 (pods labelled `app.kubernetes.io/name: flint-forge-postgres`, port `5432`) | platform |
| `argocd` | Argo CD and Sellbird's Application object | platform |

Sellbird's NetworkPolicy selects these namespaces by their
`kubernetes.io/metadata.name` label and the pods by the labels above. Renaming any
of them is a contract change.

Sellbird's own pods carry `app.kubernetes.io/name: sellbird`. The migration Job's
pods also carry `app.kubernetes.io/component: migrate`; the long-running pods carry
`app.kubernetes.io/component: app`.

## Database provisioning

Sellbird gets its own database on the shared flint-forge Postgres 18 instance,
isolated from the `flint` database and every other application by database and
role. It is single tenant: one Sellbird workspace per database. Row-level security
is deferred (ADR 0001).

The platform creates, once, before Sellbird's first sync:

| Object | Name | Properties |
|---|---|---|
| Migration role | `sellbird_migrate` | `LOGIN`, owns the `sellbird` database and therefore its `public` schema; `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`; `CONNECTION LIMIT 2` |
| Runtime role | `sellbird_app` | `LOGIN`; `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`; `CONNECTION LIMIT 20`; no DDL anywhere |
| Database | `sellbird` | `OWNER sellbird_migrate`, `ENCODING 'UTF8'`, `TEMPLATE template0` |

Grants, run by the platform as a superuser (passwords come from the operator and
are never committed anywhere):

```sql
CREATE ROLE sellbird_migrate LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD :'migrate_password';
CREATE ROLE sellbird_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 20 PASSWORD :'app_password';
CREATE DATABASE sellbird OWNER sellbird_migrate ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE sellbird FROM PUBLIC;
GRANT CONNECT ON DATABASE sellbird TO sellbird_app;

\connect sellbird
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO sellbird_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sellbird_migrate IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sellbird_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sellbird_migrate IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO sellbird_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sellbird_migrate IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO sellbird_app;
ALTER ROLE sellbird_app IN DATABASE sellbird SET statement_timeout = '30s';
ALTER ROLE sellbird_app IN DATABASE sellbird SET idle_in_transaction_session_timeout = '60s';
```

Rules both sides rely on:

- Every table, sequence and function in `sellbird` is created by `sellbird_migrate`,
  so the default privileges above apply to all of them. Sellbird's migrations MUST
  NOT grant anything beyond these and MUST NOT create roles.
- `sellbird_app` cannot `CREATE`, `ALTER`, `DROP` or `TRUNCATE`. The runtime code
  MUST NOT run DDL; it fails closed if the schema version is not the one it expects.
- Sellbird needs no extension. It MUST NOT run `CREATE EXTENSION`, and it MUST NOT
  rely on the image's preloaded `pg_cron`, `pg_net` or `flint_llm` (configured for
  the `flint` database only).
- Connection strings use the shape
  `postgresql://<role>:<password>@<pg-host>:5432/sellbird?sslmode=require&application_name=sellbird`.
  `<pg-host>` is the platform's in-cluster Postgres Service name. `sslmode` is at
  least `require`; `verify-full` when the platform serves a certificate Sellbird can
  verify (open question 3).
- No connection pooler is assumed. Sellbird keeps its own pool within the runtime
  role's connection limit.

The two connection strings reach Sellbird only through the Secrets in
[Secrets](#secrets). The migration flow is in [Migration flow](#migration-flow).

## Identity (Kratos)

Kratos is shared and platform-owned. For Sellbird the platform MUST configure:

| Setting | Value | Why |
|---|---|---|
| `selfservice.flows.registration.enabled` | `false` | operator-only sign-in; nobody can create an account |
| `selfservice.methods.password.enabled` | `true` | first factor |
| `selfservice.methods.totp.enabled` | `true` | second factor (WebAuthn MAY also be enabled) |
| `selfservice.methods.lookup_secret.enabled` | `true` | recovery codes for the second factor |
| `session.whoami.required_aal` | `highest_available` | a session without the second factor gets no identity from `whoami`, so flint-gate refuses it |
| `selfservice.flows.settings.required_aal` | `highest_available` | changing credentials needs the second factor |
| `selfservice.flows.recovery.enabled` | `false` | an email account alone must not reset access; recovery is through the admin API |
| `selfservice.allowed_return_urls` | includes `https://sellbird.example.test/` | return to Sellbird after sign-in |
| Identity schema traits | `email` only (password identifier and TOTP account name) | no trait may be named `iss`, `sub`, `aud`, `exp`, `iat`, `nbf`, `jti`, `aal` or `kid`, because flint-gate merges traits into the tokens it mints |
| Admin API | cluster-internal only, never routed through the Gateway or flint-gate | it can create identities and sessions |

The Kratos public API and the login UI are served on the platform's auth host,
`auth.example.test`. Session cookies are described in
[Session cookie domain](#session-cookie-domain).

An authenticated session at `aal2` is the only state that reaches Sellbird. A
password-only (`aal1`) session MUST NOT.

## Operator identity provisioning

There is exactly one allowlisted identity: the operator's. The operator creates it
through the platform's Kratos admin API from inside the cluster (for example with a
port-forward):

1. `POST /admin/identities` with the platform's schema id, `traits.email` set to an
   address the operator owns, `state: active`, and no credentials in the body.
2. `POST /admin/recovery/code` for that identity; the operator uses the one-time
   code to set a password in the browser.
3. The operator signs in and enrols TOTP in the settings flow, then saves the
   recovery codes offline. The next sign-in is `aal2`.
4. The operator copies the identity's `id` (a UUID) into the platform overlay's
   `SELLBIRD_GATE_ALLOWED_SUBS` (see [Gateway configuration values](#gateway-configuration-values)).

The operator's email address and identity id MUST NOT appear in this repository,
its commits, issues or pull requests. In examples here the id is
`00000000-0000-4000-8000-000000000001`.

## Gateway (flint-gate)

All browser traffic for Sellbird enters through the shared Gateway, which routes
the Sellbird hostname to flint-gate, never directly to Sellbird. flint-gate:

1. authenticates the request with its `kratos_session` provider (Kratos
   `GET /sessions/whoami` with the `ory_kratos_session` cookie);
2. on success, mints a token as described in [Minted claims](#minted-claims) and
   forwards the request to Sellbird with `Authorization: Bearer <token>`;
3. on failure, does not forward the request. Whether it answers 401 or redirects to
   the login UI is the platform's choice.

flint-gate forwards some request headers upstream, including the browser's
`Cookie` header, and adds its own `x-flint-*` headers. Sellbird MUST ignore all
cookies, every `x-flint-*` header, `X-Forwarded-*` and `Forwarded`, and any other
identity-looking header. The bearer token is the only credential Sellbird accepts
in hosted mode. Gateway mode is chosen by configuration only, never by a request
header.

## Issuer and JWKS

| Item | Value |
|---|---|
| Signing algorithm | `RS256` only (flint-gate `jwt.signing_algorithm: RS256`) |
| Issuer string (`iss`) | `https://gate.example.test`, compared by exact string match |
| JWKS URL | `http://flint-gate.flint-gate.svc.cluster.local:4456/.well-known/jwks.json` |
| JWKS URL shape | `http://<gate-service>.<gate-namespace>.svc.cluster.local:<proxy-port>/.well-known/jwks.json` |
| Key ids | every published RSA key has a non-empty `kid`, `kty: RSA`, `use: sig`, `alg: RS256` |
| Key overlap on rotation | old and new keys both published for at least 10 minutes |

Sellbird's verifier MUST:

- fetch keys only from the configured JWKS URL, never from a token's `jku`, `x5u`
  or `jwk` header;
- choose the algorithm from its own allowlist (`RS256`), never from the token
  header, and reject `none` and every HMAC algorithm;
- select the key by `kid` and reject a token with no `kid` or an unknown `kid`
  after at most one refresh;
- refresh the JWKS at most once every 60 seconds on an unknown `kid`, cache it for
  at most 5 minutes, and refuse a JWKS response over 64 KiB;
- fail closed (401) when the JWKS cannot be fetched and no cached key matches.

The JWKS is fetched over plain HTTP inside the cluster; the NetworkPolicy in
[NetworkPolicy](#networkpolicy) is what keeps that path to flint-gate alone.

## Minted claims

flint-gate mints one token per forwarded request through the `claims_enhancement`
hook with `mint_jwt.enabled: true` on Sellbird's routes. The header and claims are:

| Claim | Where | Value | Sellbird checks |
|---|---|---|---|
| `alg` | header | `RS256` | equals `RS256` |
| `kid` | header | the signing key's id, present in the JWKS | present and resolvable |
| `iss` | payload | `https://gate.example.test` | exact match |
| `aud` | payload | `sellbird` (a single string, set by the route's `additional_claims`) | exact match |
| `sub` | payload | the Kratos identity id (UUID) | in `SELLBIRD_GATE_ALLOWED_SUBS` |
| `exp` | payload | `iat` + effective TTL, TTL at most `300` seconds | in the future, with at most 30 seconds leeway |
| `iat` | payload | issue time | not in the future beyond 30 seconds leeway |
| `jti` | payload | random UUID | none required |
| `aal` | payload | `aal2` (from `{{ identity.aal }}` in `additional_claims`) | SHOULD equal `aal2` (open question 4) |

Route hook configuration Sellbird's route file uses:

```yaml
hooks:
  pre_request:
    - type: claims_enhancement
      config:
        mint_jwt:
          enabled: true
          additional_claims:
            aud: "sellbird"
            aal: "{{ identity.aal }}"
```

The platform MUST set flint-gate's `jwt.default_ttl_seconds` to `300` or less (it
applies to every route), keep `jwt.issuer` equal to the issuer string above, and
sign with RS256.

flint-gate also copies identity traits (such as `email`) into the token. Sellbird
ignores every claim not listed above, maps a verified token to its `user`
principal, and MUST NOT log the token or any claim other than `sub`.

## Route ownership

- Sellbird owns `infra/flint-gate/sellbird-routes.yaml`: a site with id `sellbird`,
  `domains: ["sellbird.example.test"]`, `default_upstream:
  "http://sellbird.sellbird.svc.cluster.local:5555"`, `default_auth:
  kratos_session`, and routes that send every path and method to that upstream
  with the hook in [Minted claims](#minted-claims). It contains no anonymous or
  passthrough route on the Sellbird site.
- The platform applies that file from this repository at a pinned commit and
  overrides only `sites[].domains` with the real hostname. Any other difference is a
  contract change.
- The platform owns the `kratos_session` provider, the `jwt` block, the auth host's
  routes (Kratos self-service and login UI passthrough) and flint-gate's admin port
  (`4457`), which is never exposed.
- Sellbird's Service is `sellbird` in namespace `sellbird`, port name `http`, port
  `5555`.

## Hostname and certificate

| Item | Value | Owner |
|---|---|---|
| Public hostname | `sellbird.example.test` (placeholder; the real one is only in the platform repo) | platform |
| Gateway listener | HTTPS on 443 for that hostname on the shared Gateway | platform |
| HTTPRoute | that listener to the flint-gate Service on port `4456` | platform |
| TLS certificate | cert-manager Certificate for that hostname, Secret in the Gateway's namespace | platform |
| DNS record | created when the listener is attached | platform, operator-approved |

The shared cluster's external-dns has no domain filter and an upsert-only policy,
so attaching the listener publishes a DNS record that stays. Attaching it is an
operator-approved action.

Sellbird reads the hostname from `SELLBIRD_PUBLIC_HOST` and accepts only that
`Host` and the `https://` Origin built from it. This repository contains no
HTTPRoute, listener or Certificate for Sellbird.

## Session cookie domain

| Setting | Value |
|---|---|
| Cookie name | `ory_kratos_session` (flint-gate `kratos_session.session_cookie`) |
| Kratos `cookies.domain` and `session.cookie.domain` | `example.test` (the parent of the auth host and `sellbird.example.test`) |
| `session.cookie.same_site` | `Lax` |
| `session.cookie.secure` / `http_only` | `true` / `true` |
| `session.lifespan` | at most `24h` |

The parent-domain cookie lets one shared Kratos serve several application hosts.
Every host under that parent receives the cookie, so every application host under
it MUST sit behind flint-gate or ignore the cookie, as Sellbird does. The browser's
cookie is a credential for flint-gate only, never for Sellbird.

## Secrets

All Secrets below are in namespace `sellbird`, created by the operator by hand,
never committed, never managed or pruned by Argo CD, and referenced from manifests
by name and key through `secretKeyRef` only.

| Secret | Key | Consumer | Content |
|---|---|---|---|
| `sellbird-db-migrate` | `SELLBIRD_DATABASE_URL` | migration Job only | connection string for `sellbird_migrate` |
| `sellbird-db-app` | `SELLBIRD_DATABASE_URL` | Sellbird app container only | connection string for `sellbird_app` |
| `sellbird-claude` | `CLAUDE_CODE_OAUTH_TOKEN` | Sellbird app container only | see [AI credential](#ai-credential) |
| `sellbird-providers` | provider keys as named in `.env.example` (for example `REOON_API_KEY`, `SMTP_PASSWORD`) | Sellbird app container only, each key `optional: true` | the email provider, verifier and discovery keys the operator uses |

The migration Job MUST NOT receive `sellbird-db-app`, `sellbird-claude` or
`sellbird-providers`. The app container MUST NOT receive `sellbird-db-migrate`.

Platform-side secrets (Postgres superuser, Kratos cookie and cipher secrets,
flint-gate's signing key) live in platform namespaces. Sellbird never references
them.

## AI credential

- Secret `sellbird-claude`, key `CLAUDE_CODE_OAUTH_TOKEN`, holding the token the
  operator creates with `claude setup-token` on their own machine (decision D4).
- It reaches the Sellbird app container only as the environment variable
  `CLAUDE_CODE_OAUTH_TOKEN` through `env.valueFrom.secretKeyRef`. It MUST NOT be
  mounted as a file, MUST NOT be written to disk (not under `/data`, not under
  `$HOME`), MUST NOT be logged, printed, returned by the dashboard API, stored in
  the database or placed in a ConfigMap.
- With the variable unset, the brain reports its documented missing-login error and
  does not fall back to a credential file.
- Codex is not used in the cluster.
- Rotation is manual: the operator creates a new token, replaces the Secret's value
  and restarts the Deployment. Whether headless server use of a subscription login
  is allowed by the provider's terms was not verified; the operator owns that risk
  (D4).

## Gateway configuration values

Non-secret settings reach the app container from ConfigMap `sellbird-gateway`,
which lives in the platform's production overlay (the example overlay in this
repository uses the placeholders):

| Key | Example value | Meaning |
|---|---|---|
| `SELLBIRD_DASHBOARD_MODE` | `gateway` | selects gateway mode; the only way to select it |
| `SELLBIRD_PUBLIC_HOST` | `sellbird.example.test` | accepted `Host`; Origin is `https://` plus this |
| `SELLBIRD_GATE_ISSUER` | `https://gate.example.test` | expected `iss` |
| `SELLBIRD_GATE_AUDIENCE` | `sellbird` | expected `aud` |
| `SELLBIRD_GATE_JWKS_URL` | `http://flint-gate.flint-gate.svc.cluster.local:4456/.well-known/jwks.json` | pinned JWKS location |
| `SELLBIRD_GATE_ALLOWED_SUBS` | `00000000-0000-4000-8000-000000000001` | comma-separated allowlisted Kratos identity ids |

The algorithm allowlist (`RS256`) is fixed in Sellbird's code, not configurable.

## Overlay location and pin format

| Item | Value |
|---|---|
| Platform repository | named by this repository's Actions variable `SELLBIRD_PLATFORM_REPO`, value `<owner>/<repo>` (placeholder `example-org/platform`); never written as a literal in this repository |
| Overlay directory | `apps/sellbird/overlays/production` in the platform repository |
| File the bot edits | `apps/sellbird/overlays/production/kustomization.yaml` |
| Branch | the platform repository's default branch, `main` |
| Writer | the deploy GitHub App; client id in variable `SELLBIRD_DEPLOY_APP_CLIENT_ID`, private key in secret `SELLBIRD_DEPLOY_APP_PRIVATE_KEY` of this repository's `production` environment |

The production overlay's `kustomization.yaml` has exactly one `images` entry for
Sellbird, matching the base's logical image name `sellbird`:

```yaml
resources:
  - https://github.com/example-owner/sellbird//infra/k8s/base?ref=0123456789abcdef0123456789abcdef01234567
images:
  - name: sellbird
    newName: ghcr.io/example-owner/sellbird
    newTag: "0123456789abcdef0123456789abcdef01234567"
    digest: sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

Pin rules:

- `newTag` is the full 40-character commit SHA the image was built from, quoted,
  matching `^[0-9a-f]{40}$`.
- `digest` is the pushed image's manifest digest, matching `^sha256:[0-9a-f]{64}$`.
- A pin commit changes exactly those two lines and nothing else. Its message is
  `chore(sellbird): pin <newTag> <digest>`.
- Never backwards: the new SHA MUST differ from the pinned one and the pinned SHA
  MUST be an ancestor of it on this repository's `main`.
- The rendered Deployment image MUST carry `@sha256:`; a tag-only image is refused.
- The bot never edits `resources`. The base `ref` is moved by a reviewed pull
  request in the platform repository when Sellbird's manifests change.

The deploy App needs only Contents read and write, installed only on the platform
repository. The platform repository's ruleset lets the App push to `main` and
requires review for every other writer.

## Argo CD ownership

The platform repository owns both objects:

| Object | Name | Required settings |
|---|---|---|
| AppProject | `sellbird` | `sourceRepos`: the platform repository and this repository (for the pinned remote base); `destinations`: in-cluster server, namespace `sellbird` only; `clusterResourceWhitelist`: empty; `namespaceResourceWhitelist`: Deployment, Service, ServiceAccount, ConfigMap, NetworkPolicy, Job; Secrets are not in the list |
| Application | `sellbird` in namespace `argocd` | `project: sellbird`; source path `apps/sellbird/overlays/production` at `main`; destination namespace `sellbird`; `syncPolicy.automated` with `prune: true` and `selfHeal: true`; `CreateNamespace=false` |

Syncing into the cluster is gated on the platform phase and is an operator-approved
action.

## Migration flow

1. Sellbird's base includes Job `sellbird-migrate` annotated
   `argocd.argoproj.io/hook: PreSync` and
   `argocd.argoproj.io/hook-delete-policy: BeforeHookCreation`.
2. It runs `sellbird storage migrate` from the same pinned image, with
   `SELLBIRD_DATABASE_URL` from `sellbird-db-migrate`, and applies pending up
   migrations in order inside transactions.
3. If it fails, the sync fails and the Deployment keeps running the previous image.
4. The app then starts as `sellbird_app`. It cannot change the schema and refuses to
   start if the schema version does not match the one its code expects.
5. Down migrations are never automatic. A rollback that needs one is an operator
   action run with the migration role, before the pin is moved back by a reviewed
   change.

## NetworkPolicy

Sellbird's base ships a default-deny policy for the `sellbird` namespace and these
allowances:

| Direction | Pods | Peer | Ports |
|---|---|---|---|
| ingress | `component: app` | pods `app.kubernetes.io/name: flint-gate` in namespace `flint-gate` | TCP 5555 |
| egress | all Sellbird pods | kube-dns in `kube-system` | UDP and TCP 53 |
| egress | all Sellbird pods | pods `app.kubernetes.io/name: flint-forge-postgres` in namespace `flint-forge` | TCP 5432 |
| egress | `component: app` | pods `app.kubernetes.io/name: flint-gate` in namespace `flint-gate` | TCP 4456 (JWKS) |
| egress | `component: app` | `0.0.0.0/0` except cluster, private (RFC 1918) and link-local `169.254.0.0/16` ranges | TCP 80, 443, 465, 587, 993 (model API, email providers, prospecting) |

The migration Job gets DNS and Postgres egress only. Nothing else may reach
Sellbird's port: not the Gateway, not other namespaces.

The platform MUST allow, on its side: flint-gate egress to `sellbird` on TCP 5555,
flint-forge ingress from `sellbird` on TCP 5432, and flint-gate ingress from
`sellbird` on TCP 4456. Kubelet probes reach the pod outside these rules.

## Rotation and revocation

| Event | Action | Residual exposure |
|---|---|---|
| Remove the operator's access | remove the id from `SELLBIRD_GATE_ALLOWED_SUBS` and roll the Deployment; revoke Kratos sessions with `DELETE /admin/identities/<id>/sessions` | tokens already minted stay valid for at most 300 s |
| flint-gate signing key rotation | publish the new key beside the old one, switch signing, keep the old key published for at least 10 minutes | none, if the overlap is kept |
| Suspected signing key leak | remove the key from the JWKS at once | Sellbird drops it within its 5-minute cache window |
| Database password rotation | `ALTER ROLE ... PASSWORD`, update the matching Secret, restart the consumer | none |
| AI token rotation | new `claude setup-token`, replace `sellbird-claude`, restart | the old token until the provider revokes it |

## Out of scope

- Deploying the shared platform services themselves (Postgres, Kratos, Hydra,
  flint-gate, flint-realtime-fabric, ElectricSQL, the Gateway): platform phase.
- Ory Hydra and OAuth flows for Sellbird; Sellbird uses Kratos sessions checked by
  flint-gate (D11).
- Changes to the flint-gate or flint-forge repositories (D6).
- Row-level security, multiple tenants or multiple users in the `sellbird` database.
- Automated backups, high availability and autoscaling (D12); Sellbird runs one
  replica.
- Codex in the cluster.
- Moving the operator's real local data.
- Email provider OAuth tokens that Sellbird itself stores at runtime (for example a
  Gmail refresh token); their handling in the cluster is not decided here.

## Placeholders

| Placeholder | Stands for | Real value lives in |
|---|---|---|
| `sellbird.example.test` | Sellbird's public hostname | platform repository overlay and route override |
| `auth.example.test` | Kratos public API and login UI host | platform repository |
| `example.test` | parent cookie domain | platform repository Kratos config |
| `https://gate.example.test` | flint-gate issuer string | platform repository flint-gate config |
| `example-owner` | GitHub and registry owner of this repository | Actions context at run time |
| `example-org/platform` | the platform repository | Actions variable `SELLBIRD_PLATFORM_REPO` |
| `00000000-0000-4000-8000-000000000001` | the operator's Kratos identity id | platform overlay ConfigMap |
| `<pg-host>` | the in-cluster Postgres Service name | operator-created Secrets |
| `0123456789abcdef...` | a commit SHA or image digest | the deploy bot's pin commit |
