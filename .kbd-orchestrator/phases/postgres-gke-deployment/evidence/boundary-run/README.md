# B4 boundary run, attempt 1

- Authorized: 2026-11-18T20:14:20Z (contract 04f6a6fd…)
- Candidate: commit 70b4ccb5380acb218f26455f55943fcddaa986bd (tree 12b4741ae794), frozen 2026-11-18T20:15:19.333102+00:00
- Result: **FAIL** at packet command `build` (`docker build -t sellbird:boundary .`, exit 1).

## What happened

1. `preflight` — PASS (pinned tool images pulled).
2. `build` — FAIL. Stage-1 step 4/12 installs requirements and the hosted/postgres
   extras (succeeded; `import jwt, psycopg` printed ok), then runs
   `playwright install --with-deps chromium`, which exited 127: Playwright's bundled
   Node driver could not load `libatomic.so.1`, absent from the arm64 python slim base.
3. Every later command (stand-in, scenario commands, 13 negative controls) was not
   run, per the contract's stop condition. All 13 scenarios are NOT_EXERCISED.

No container, volume, image or `.env` was created, so there was nothing to clean up.

Raw output: `raw/01-preflight.log`, `raw/02-build.log`; identities: `freeze.json`.

# Attempt 2 — B5 repair 1 (authorized 2026-11-18T20:23:11Z)

- Repair: commit 39ab979 installs `libatomic1` before `playwright install`.
- `build` — PASS (image sha256:764bb477…, arm64).
- `run-standin` — **BLOCKED**: host port 55432 already allocated. Another local
  project's containers (`aso-prior-auth-demo`, up 4 days) hold 55432, 4456 and
  4433-4434, which the stand-in publishes. Not a product observation.
- Nothing after it ran. Cleanup: `docker compose down -v` (sellbird-local only),
  `infra/local/.env` deleted; image kept for the next attempt.
