# Design: Hosted gateway mode: trust a flint-gate JWT, keep local token mode unchanged

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 4). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Add a config-selected gateway mode (never chosen by request headers) that allows a non-loopback bind, accepts the configured public Host and https Origin, verifies the gate-minted JWT against a pinned JWKS (iss, aud, kid, alg, exp) and an allowlisted Kratos sub, maps it to principal user, ignores cookies and unverified x-flint-*/forwarded headers, disables the agent token, and never prints the dashboard token. Local token mode stays the default and still refuses non-loopback binds.

### Structure

- The local guard (`sellbird/dashboard_auth.py`) is not modified. Gateway mode is a separate guard, `sellbird/auth/gateway_guard.py:GatewayGuard`, swapped in through the existing `dashboard.build_app(guard=...)` seam by `dashboard.build_gateway_app`. The module-level `dashboard.app` keeps the token guard in every mode, so local behaviour cannot drift.
- `sellbird/auth/config.py` reads the mode and settings from the environment once, at startup. `sellbird/auth/jwks.py` is the pinned key cache; `sellbird/auth/gate_token.py` the verifier (PyJWT with `cryptography`, optional extra `hosted` in pyproject.toml and a line in requirements.txt; it was already a transitive dependency of `mcp`).
- `dashboard.start_dashboard` checks the mode first. `local` (or unset) runs the unchanged loopback/token path; `gateway` runs `_start_gateway_dashboard`, which never reads, creates or prints the dashboard token and writes no `data/dashboard.json` (that file only serves the local MCP agent).

### Configuration interface

| Variable | Required in | Rule |
|---|---|---|
| `SELLBIRD_DASHBOARD_MODE` | always optional | unset/empty/`local` = local; `gateway` = gateway; anything else stops startup |
| `SELLBIRD_PUBLIC_HOST` | gateway | bare `host` or `host:port`, compared exactly (lowercased) with the `Host` header; Origin must be `https://` + it |
| `SELLBIRD_GATE_ISSUER` | gateway | exact `iss` |
| `SELLBIRD_GATE_AUDIENCE` | gateway | exact `aud` (a single string) |
| `SELLBIRD_GATE_JWKS_URL` | gateway | http(s), a host, no credentials, no fragment |
| `SELLBIRD_GATE_ALLOWED_SUBS` | gateway | comma-separated canonical UUIDs, 1 to 16 |
| `SELLBIRD_CONTAINER` | image | `1` in the Dockerfile (request to the image owner); with `KUBERNETES_SERVICE_HOST` or `container` it marks "inside a container", where local mode prints no unlock link and `--url` is refused |

No CLI flag selects the mode (the contract makes the environment variable the only selector). In gateway mode `--host` accepts any IP address (e.g. `0.0.0.0`) or `localhost`, never a name to resolve; in local mode it is refused exactly as before.

### How each refusal is enforced (gateway mode)

| Input | Where | Result |
|---|---|---|
| `Host` not exactly the public host, or repeated | guard step 1 | 400 |
| `Origin` present and not `https://<public host>`; `Sec-Fetch-Site` other than `same-origin`/`none` | guard step 2 | 403 |
| `POST`/`PUT`/`PATCH`/`DELETE` without that `Origin` | guard step 2 | 403 (the parent-domain Kratos cookie makes sibling hosts same-site) |
| no `Authorization`, two of them, non-Bearer, or not a compact JWS (8 KiB cap) | guard step 3 / verifier | 401, empty body |
| `alg` not `RS256` (incl. `none`, HS*), `jku`/`x5u`/`jwk`/`x5c`/`crit` present, no `kid` | verifier, before any key lookup | 401 |
| unknown `kid` | JWKS cache: at most one refresh per 60 s (empty/expired cache: one try per 5 s), keys older than 5 min never used, >64 KiB / redirect / non-200 / >32 keys refused, only RSA >= 2048-bit `sig` RS256 keys with a unique `kid` | 401 |
| bad signature, `iss`, `aud` (lists refused), missing `exp`/`iat`/`iss`/`aud`/`sub`, expired, `iat` or `nbf` in the future (30 s leeway), `exp - iat` > 300 s | verifier | 401 |
| `sub` not a canonical UUID or not allowlisted | verifier | 401 (only `sub` is logged) |
| `aal` present and not `aal2` | verifier | 401 |
| Cookie, `x-flint-*`, `X-Forwarded-*`, `Forwarded`, any mode-looking header | never read by the guard; uvicorn runs with `proxy_headers=False` | no effect |
| the dashboard token or the agent token as Bearer | not a JWS; the token stores are never consulted | 401 |
| body on a mutation that is not `application/json` | guard step 5 | 415 |
| `/api/instance` (local MCP handshake) | not public in gateway mode | 401 |

A verified token sets `request.state.principal = "user"` and `request.state.gate_sub`. `GET /api/auth/whoami` (gateway mode only, behind the guard) returns `{"mode": "gateway", "principal": "user", "sub": "<id>"}`; the e2e oracle reads it. Any unexpected exception in verification is a 401.

### E2E environment interface (`tests/test_gateway_mode_e2e.py`)

The module skips when `SELLBIRD_GATEWAY_URL` is unset. Once it is set, every other variable is required and a missing one fails (no silent skip at the boundary). The gateway engineer's stand-in script (`scripts/local/`) provides them from the uncommitted `.env`:

| Variable | Meaning |
|---|---|
| `SELLBIRD_GATEWAY_URL` | flint-gate proxy URL in front of the `sellbird:boundary` container (plan: `http://localhost:4456`) |
| `SELLBIRD_E2E_HOST` | optional `Host` for gateway requests (the site domain flint-gate routes on) |
| `SELLBIRD_E2E_ALLOWED_SUB` | the allowlisted Kratos identity id created by the setup script (the oracle's expected principal) |
| `SELLBIRD_E2E_SESSION_COOKIE` | `Cookie` header value of an aal2 session for that identity |
| `SELLBIRD_E2E_OTHER_SESSION_COOKIE` | `Cookie` header value of an aal2 session for a second identity that is not allowlisted |
| `SELLBIRD_E2E_DIRECT_URL` | Sellbird's own published port, bypassing flint-gate |
| `SELLBIRD_E2E_PUBLIC_HOST` | the container's `SELLBIRD_PUBLIC_HOST`, sent as `Host` on direct requests |
| `SELLBIRD_E2E_GATE_KEY_FILE` | path to the stand-in flint-gate's RS256 private key (generated per run, never committed) |
| `SELLBIRD_E2E_GATE_KID` | its `kid` in the JWKS |
| `SELLBIRD_E2E_GATE_ISSUER` | flint-gate's issuer string |

Through the gate: the allowlisted session resolves to the allowlisted id; forged `x-flint-user-id`/`X-Forwarded-User` don't change it; no session (with a forged identity header) and the non-allowlisted session are refused with 401 and no data. Directly: a gate-key-signed valid token is the positive control; no token, forged identity header, cookie alone, wrong `aud`, expired and non-allowlisted `sub` are refused with 401 and no data. Direct requests exist because flint-gate replaces any client `Authorization`, so wrong-aud/expired tokens can only reach Sellbird past the gate.

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

Changed baseline test files (justified): none. `tests/test_dashboard_auth.py` is untouched; the new files are `tests/test_gateway_mode_local.py` and `tests/test_gateway_mode_e2e.py`.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.
- Test environment: the baseline local tests assume `SELLBIRD_DASHBOARD_MODE` is unset; a boundary shell that exports it for the stand-in must not leak it into the pytest run of `tests/test_dashboard_auth.py` (`tests/test_gateway_mode_local.py` clears it itself).
- Kubelet probes: in gateway mode every request must carry the public `Host`, so an `httpGet` probe needs a `Host` header or the probe should be `tcpSocket`. Coordinate with the image/manifest owners (changes 6 and 9).
- Browser UI: the UI attaches no token in gateway mode, flint-gate adds its own, and a refusal is a bodiless 401. Whether the lock screen copy fits gateway mode is for the frontend owner.

## Open Questions

- `aal`: the contract says Sellbird SHOULD check `aal == aal2` (its open question 4). The verifier refuses a token whose `aal` is present and not `aal2`, and accepts a token without `aal` (Kratos `whoami.required_aal: highest_available` is the primary control). Requiring the claim would need the spec to say MUST.
- Token lifetime: the verifier also refuses `exp - iat` > 300 s, from the contract's "TTL at most 300 seconds". A longer platform TTL would be refused, which is intended.
