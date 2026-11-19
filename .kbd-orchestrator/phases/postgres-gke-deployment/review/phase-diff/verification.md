# Independent review — producer verification of judge findings

Judge: mimo-v2.6-pro (Xiaomi) via rest-gateway http://localhost:4000/v1. Producer: claude-opus-5-5.
`cross_model_check` reads `unverified-producer-unknown` because the packets carried no
canonical `producer_identity` tuple; the two models are from different vendors.
Packets: cumulative diff 25ec839..ebf4e3b split into storage, auth-gateway, platform, local-scripts.
Judge verdicts: BLOCK, BLOCK, BLOCK, PASS (4 CRITICAL, 15 WARNING, 6 SUGGESTION).

This file is the producer's check of the judge's claims. It is not independent; the operator decides.

## CRITICAL findings — none survived verification

| # | Finding | Producer check | Proposed disposition |
|---|---|---|---|
| C1 | dialect.py:304 INSERT OR REPLACE ≠ SQLite semantics | Only caller is state.py:1483 `settings(key, value, updated_at)`; `key` is the sole unique constraint; all user columns listed. Only difference: SQLite assigns a new `rowid`, Postgres keeps it; nothing reads settings.rowid. Latent for future callers. | WARNING (latent) |
| C2 | sellbird-routes.yaml lacks Kratos passthrough | proposal.md sentence says so, but design.md:23 deliberately places the passthrough on the platform's auth host because the platform contract forbids passthrough on the Sellbird site; file header says the same. Judge's packet had proposal/tasks/spec, not design.md. Proposal wording is stale. | Not a defect; fix stale proposal text at archive |
| C3 | Dockerfile:81 default SOURCE_URL names a real GitHub owner | It is the project's own upstream repository URL, already referenced in README, pyproject.toml, CODE_OF_CONDUCT and others before this phase; CI overrides it with --build-arg. Not prospect/personal data. | Not a defect (could default to the fork; operator choice) |
| C4 | (platform) .dockerignore omits `!skills/**` (WARNING, checked with the CRITICALs) | False: .dockerignore at HEAD has both `!skills/` and `!skills/**`. | Rejected |

## WARNINGs judged real or plausible (candidate follow-ups)

- W1 images.yml:217 planted-secret control matches `endswith("/app/...")`; if Trivy reports image paths without a leading slash the control step always fails. Never exercised (CI has not run on GitHub; SHIP-001 covers digest pins, not Trivy). Fails closed: blocks publishing, ships nothing bad. PLAUSIBLE.
- W2 storage_postgres/errors.py:81 fallback raises `message_primary` verbatim, contradicting the module's "never echoes values" docstring. REAL (log hygiene).
- W3 auth/config.py:123 JWKS URL accepts http. In-cluster traffic to flint-gate is plain HTTP by design of the contract, but nothing forces https outside the cluster. REAL hardening gap.
- W4 networkpolicy.yaml:72 DNS egress only to kube-dns; NodeLocal DNSCache (169.254.20.10) would be blocked. PLAUSIBLE, depends on cluster config.
- W5 migrate-job.yaml:22 PreSync hook can run before NetworkPolicies on first sync. PLAUSIBLE.
- W6 storage_postgres/__init__.py:86 `exists` maps auth/unreachable errors to False. REAL (silent failure).
- W7 errors.py:40 FK message wrong for RESTRICT refusals; dialect NULLS rewrite vs window frames; data-modifying CTE classed read-only. Latent (no current caller found).
- W8 infra/kratos/kratos.yml http base_url (local stand-in only); hosting.md omits PyYAML prerequisite.

Suggestions recorded in findings-*.json; none blocking.

## Confirmation review of B5 repair 6 (7c0a084)

Judge mimo-v2.6-pro, packet `packet-repair6.json`, findings `findings-repair6.json`: BLOCK (1 CRITICAL, 1 WARNING, 1 SUGGESTION). This is my check of it, written by the producer session; it is not independent.

- **CRITICAL: `exists()` can never see a sqlstate.** Does not hold. `translate_error` (sellbird/storage_postgres/errors.py:58-65, unchanged, so not in the diff the judge saw) sets `err.sqlstate = getattr(exc, "sqlstate", None)` on every translated error. Run evidence: `test_an_unexpected_postgres_error_never_echoes_the_value` asserts `sqlstate == "22P02"` and passed against real Postgres in attempt 9 (a9-04-scn-suite.log: 3958 passed, the module not among the skips). `42P01` (unmigrated) is raised by a query, so it carries the state and `exists()` returns False.
- **The finding's underlying point, partly real:** a database that does not exist (`3D000`) fails at connect time. psycopg raises that as `OperationalError("connection failed: ...")` with no result attached (psycopg/generators.py:93), so `sqlstate` is None there. `exists()` therefore **raises** for a missing database instead of returning False. Its docstring and the `_NOT_THERE` comment say otherwise. Fails loud, not silent; the dashboard catches it and logs. Recorded as follow-up F1: correct the docstring, or detect `3D000` from the connect error.
- **WARNING: the 22P02 assertion fails on the new code.** Does not hold, for the same reason; it passed in attempt 9.
- **SUGGESTION: no CHANGELOG entry.** Fair. The `changelog-and-docs` warning constraint applies. Recorded as follow-up F2, for the docs change that also carries the phase's CHANGELOG work.

Disposition: no CRITICAL survives verification. The operator directed closing the phase once this review finished, unless a CRITICAL held up.
