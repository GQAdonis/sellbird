# Design: Make the configured test command runnable and the baseline suite green

## Context

See the phase assessment (`.kbd-orchestrator/phases/postgres-gke-deployment/assessment.md`) and plan (change 1). Operator decisions D1–D12 and the plan-stage decisions (restated goals adopted, single tenant with RLS deferred, production overlay in the platform repository) apply.

## Decisions

Install the dev extras into .venv with `uv sync --extra dev` (pre-approved; may create or update uv.lock) so `.venv/bin/python -m pytest -q` runs, and make the two baseline failures deterministic without weakening them: tests/test_compliance_footer.py::test_a_long_french_reply_is_quick (asserts a long French reply is classified in under 2 s, line 873) and tests/test_people_finder.py::test_nested_testimonials_are_bounded (asserts 2,000-level nested testimonial HTML is scanned in under 1.0 s, line 413). Both guard against super-linear (pathological) processing; the replacement must still fail on a quadratic implementation, e.g. by comparing time at n and 2n or bounding work rather than wall-clock on a slow volume. Their pre-change digests and the 3,729 baseline test IDs are recorded as fixtures so the boundary can prove no test was deleted and these two kept their intent.

## Verification

Implemented in its plan round and verified once at the phase boundary (VLBV). Scenarios and negative controls are defined in the plan's coverage table and the adopted contract. Baseline test files changed by this change must be listed here with a justification so the boundary's source-digest check can accept them.

Changed baseline test files (justified): none yet.

## Risks

- Real names: no real person's or business's name, email, phone, address or domain in code, tests, docs or commits; use fictional example.com / example.test data.
- Secrets: credentials only through operator-created Secrets or an uncommitted local .env.

## Open Questions

None that change what gets built; the platform contract's operator agreement is tracked as a boundary receipt.
