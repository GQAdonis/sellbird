"""Cohorts on both backends against hand-authored expectations (fixtures/cohorts.json)."""

import json
from pathlib import Path

import pytest

from sellbird.models.company import Company
from tests.storage_contract.backends import locator, state  # noqa: F401  (fixtures)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "cohorts.json").read_text())


async def _seed(state) -> dict[str, str]:
    for signal in FIXTURE["signals"]:
        await state.upsert_signal_code(signal["code"], value_type=signal["value_type"])
    ids = {}
    for c in FIXTURE["companies"]:
        ids[c["key"]] = await state.add_company(Company(name=c["name"], domain=c["domain"]))
    for o in FIXTURE["observations"]:
        await state.add_observation(
            o["code"], company_id=ids[o["company"]], value_num=o["value_num"],
            value_text=o.get("value_text", ""), confidence=o.get("confidence", 1.0),
            observed_at=o["at"])
    return ids


@pytest.mark.asyncio
@pytest.mark.parametrize("case", FIXTURE["cohorts"], ids=lambda c: c["why"][:40])
async def test_cohort_matches_the_hand_authored_expectation(state, case):
    ids = await _seed(state)
    names = {v: k for k, v in ids.items()}
    found = await state.cohort(case["require"], case["exclude"],
                               min_confidence=case["min_confidence"])
    assert sorted(names[i] for i in found) == sorted(case["expected"])


@pytest.mark.asyncio
async def test_ranked_companies_per_phrase(state):
    ids = await _seed(state)
    names = {v: k for k, v in ids.items()}
    for case in FIXTURE["ranked_for_phrase"]:
        found = await state.ranked_company_ids(case["code"], case["phrase"])
        assert sorted(names[i] for i in found) == sorted(case["expected"]), case["phrase"]


@pytest.mark.asyncio
async def test_signal_counts_are_the_cohort_sizes(state):
    await _seed(state)
    counts = {r["signal_code"]: r["companies"] for r in await state.signal_counts()}
    assert counts == FIXTURE["signal_counts"]
