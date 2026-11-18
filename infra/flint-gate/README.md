# Sellbird behind flint-gate

`sellbird-routes.yaml` is Sellbird's half of the flint-gate configuration: one
site and two routes, written in flint-gate's real config schema. The platform
owns the rest of flint-gate's `config.yaml` (see `docs/platform-interface.md`,
"Gateway", "Issuer and JWKS", "Minted claims", "Route ownership").

## What the platform does with it

1. Appends `sites` and `routes` from this file to its own `config.yaml`.
2. Replaces `sites[0].domains` with the real hostname. Nothing else changes.
3. Restarts flint-gate. The flint-gate build the contract pins
   (`ghcr.io/know-me-tools/flint-gate@sha256:e67abd80…`) reads `config.yaml` once
   at startup; its file watcher only reports that a restart is needed. Routes are
   not managed through the admin API: `database.override_yaml` stays `false`,
   so a database route can never shadow these.

The platform's `config.yaml` must provide, for these routes to work:

| Key | Value |
|---|---|
| `auth_providers.kratos_session` | `type: kratos`, `base_url` = Kratos public API, `session_cookie: ory_kratos_session` |
| `jwt.signing_algorithm` | `RS256` |
| `jwt.signing_key_id` | a non-empty `kid`, published at `/.well-known/jwks.json` |
| `jwt.issuer` | `https://gate.example.test` (placeholder) |
| `jwt.default_ttl_seconds` | `300` or less (the hook has no per-route TTL; Sellbird refuses `exp - iat > 300`) |
| `server.admin_listen` | loopback or a ClusterIP-only Service; never on the Gateway |

flint-gate serves the JWKS from its database (`jwt_signing_keys`), so the key
must be seeded with `flint-gate --database-init-only` and both
`FLINT_GATE_JWT_KEY_PATH` and `FLINT_GATE_JWT_PUBLIC_KEY_PATH` set, as in
flint-gate's own `k8s/overlays/ssr/database-init-job.yaml`.

## Route truth table

| Request to `sellbird.example.test` | Result |
|---|---|
| any path, any method, aal2 Kratos session cookie | forwarded with `Authorization: Bearer <RS256, aud=sellbird, sub=identity id>`; Sellbird then checks `sub` against its allowlist |
| aal1 (password-only) session of an identity with TOTP | Kratos `whoami` answers 403, flint-gate refuses (401); not forwarded |
| no cookie, or an expired/revoked session | refused (401); not forwarded |
| client `Authorization`, `x-flint-*` headers | `x-flint-*` stripped; `Authorization` replaced by the minted token |
| any other `Host` | no Sellbird route matches |

## Deliberately not here

- **Cedar policies.** Sellbird is single-user (one allowlisted Kratos identity)
  and the contract puts that check in Sellbird's verifier. A gate-side
  `authorize` hook would need a non-empty, validated Cedar policy set loaded by
  the platform (an empty set is default-deny and would refuse everything). Adding
  one is a contract change; the agent-governance lint does not require it here,
  because `kratos` routes are not agent-reachable.
- **Streaming rules.** Sellbird's dashboard serves no SSE or AG-UI streams, so
  `stream.enabled` stays at its default (`false`).
- **Header enrichment beyond the token.** No `inject_headers`: Sellbird ignores
  every identity header except the verified bearer token.

## Local stand-in

`infra/local/` runs this file unmodified against real Kratos and flint-gate
containers (`scripts/local/make-env.sh`). The stand-in gives the Sellbird
container the network alias `sellbird.sellbird.svc.cluster.local`, so even the
upstream URL is the contract's.
