# Goals: sellbird-go-live

Seeded from: `postgres-gke-deployment/reflection.md`
Created: 2026-11-21T23:59:06Z

## Reflection proposals — not adopted scope

These are suggestions carried forward from the previous reflection. They are
not requirements: blocking scope exists only once this phase's contract is
adopted (and any later change is a signed amendment).

`phase-shared-platform` (in the new platform repo, per D11), then `phase-sellbird-go-live` in this repo:

1. **Platform repo:**
   - Gateway, flint-forge PG18 with Sellbird's database and roles, Kratos (operator-only, with MFA) and flint-gate on GKE;
   - provisioning that matches `docs/platform-interface.md`;
   - the production overlay.
2. **Go-live:**
   - history cleanup;
   - push and open a PR;
   - first runs of the CI matrix, the Postgres job and `images.yml` (fix first-run failures, including the Trivy control);
   - the GitHub App deploy bot and the protected-main ruleset.
3. **Live check:**
   - Argo CD syncs Sellbird by digest;
   - `sellbird.know-me.tools` resolves, serves TLS and requires a Kratos session (CG-1..3).
   - Also clear F1–F3, the JWKS https requirement and the NodeLocal DNS policy before the first sync.

---

## Instructions

Review and refine the goals above before running `/kbd-assess`.
Add, remove, or clarify as needed. When ready:

```
/kbd-assess sellbird-go-live
```
