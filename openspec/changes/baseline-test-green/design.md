# Design: Make the configured test command runnable and the baseline suite green

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 1). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Install the dev extras into .venv with `uv sync --extra dev` (pre-approved; may create or update uv.lock) so `.venv/bin/python -m pytest -q` runs, and make the two baseline failures deterministic without weakening them: tests/test_compliance_footer.py::test_a_long_french_reply_is_quick (asserts a long French reply is classified in under 2 s, line 873) and tests/test_people_finder.py::test_nested_testimonials_are_bounded (asserts 2,000-level nested testimonial HTML is scanned in under 1.0 s, line 413). Both guard against super-linear (pathological) processing; the replacement must still fail on a quadratic implementation, e.g. by comparing time at n and 2n or bounding work rather than wall-clock on a slow volume. Their pre-change digests and the 3,729 baseline test IDs are recorded as fixtures so the boundary can prove no test was deleted and these two kept their intent.

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

Decision (uv.lock and test command): `uv sync --extra dev` installs the dev extras into `.venv`, so `.venv/bin/python -m pytest -q` runs (pytest 8.4.2 and pytest-asyncio 0.26.0 import cleanly). `uv.lock` is NOT committed. The project's CI (`.github/workflows/tests.yml`) installs with `pip install -e ".[dev]"` on a Windows/macOS/Linux x Python 3.11/3.12 matrix and never reads `uv.lock`, so a committed lock would be a second, unused source of truth that drifts from `pyproject.toml`, and it was resolved on one platform and one interpreter. The generated file stays an untracked local artifact of the operator's uv workflow. If the project later adopts uv in CI, add the lock then with a `uv sync --locked` check.

Decision (timing tests): both tests guarded against super-linear processing with a fixed wall-clock bound (2 s and 1.0 s), which depends on disk and CPU speed and not on the algorithm. They now time the same operation at a small size and at four times that size (best of three runs each, small time floored at 1 ms) and require the larger run to cost less than 8x the smaller. A linear implementation lands near 4x; a quadratic one near 16x, so the bound separates them with a wide margin on both sides and is independent of absolute machine speed. Inputs, the functions under test and the intent are unchanged; no production code changed. The French reply test uses 5,000 and 20,000 repetitions (the original size is the larger one) and the testimonial test uses nesting depths 500 and 2,000 (the original depth is the larger one).

Boundary preflight: `scripts/boundary/preflight.sh` pulls actionlint, kustomize, yq and the Postgres 18 client from container images pinned by multi-arch index digest and exposes `sb_actionlint`, `sb_kustomize`, `sb_yq`, `sb_yq_stdin` and `sb_pg` wrappers. It installs nothing on the host.

Changed baseline test files (justified):

- `tests/test_compliance_footer.py`: `test_a_long_french_reply_is_quick` replaced its absolute `< 2` s bound with a 4x-growth ratio bound (< 8x), so it is deterministic on slow storage and still fails on a quadratic `_opt_out_reason`.
- `tests/test_people_finder.py`: `test_nested_testimonials_are_bounded` replaced its absolute `< 1.0` s bound with a 4x-depth ratio bound (< 8x), so it is deterministic on slow storage and still fails on a quadratic `drop_quoted` or `find_people`.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.

## Open Questions

None that change what gets built; the platform contract's operator agreement is tracked as a boundary receipt.
