# Make the configured test command runnable and the baseline suite green

## Why

Install the dev extras into .venv with `uv sync --extra dev` (pre-approved; may create or update uv.lock) so `.venv/bin/python -m pytest -q` runs, and make the two baseline failures deterministic without weakening them: tests/test_compliance_footer.py::test_a_long_french_reply_is_quick (asserts a long French reply is classified in under 2 s, line 873) and tests/test_people_finder.py::test_nested_testimonials_are_bounded (asserts 2,000-level nested testimonial HTML is scanned in under 1.0 s, line 413). This change serves phase goal Constraint tests-pass (blocking) and SCN-BASE-001 of KBD phase `postgres-gke-deployment`.

## What Changes

Install the dev extras into .venv with `uv sync --extra dev` (pre-approved; may create or update uv.lock) so `.venv/bin/python -m pytest -q` runs, and make the two baseline failures deterministic without weakening them: tests/test_compliance_footer.py::test_a_long_french_reply_is_quick (asserts a long French reply is classified in under 2 s, line 873) and tests/test_people_finder.py::test_nested_testimonials_are_bounded (asserts 2,000-level nested testimonial HTML is scanned in under 1.0 s, line 413). Both guard against super-linear (pathological) processing; the replacement must still fail on a quadratic implementation, e.g. by comparing time at n and 2n or bounding work rather than wall-clock on a slow volume. Their pre-change digests and the 3,729 baseline test IDs are recorded as fixtures so the boundary can prove no test was deleted and these two kept their intent.

## Capabilities

- None. This change alters no spec-level behaviour (`skip_specs: true`); it is tooling, configuration or documentation verified by boundary scenarios.

## Impact

- Scope: tests | tooling
- Depends on: none
- Owner role: `qa-engineer`
- Plan: `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md` (change 1)
