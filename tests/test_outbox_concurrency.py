"""An approved email is claimed for sending exactly once, however many senders race.

The heartbeat and the dashboard are separate writers. Each claimer here has its
own StateManager and its own database connection, and all of them try to claim
the same approved item at once; exactly one may win, every round, on both
backends. Postgres runs as the runtime role and skips, saying why, without the
test DSNs.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from sellbird.state import StateManager
from tests.storage_contract.backends import BACKENDS, fresh_locator

CLAIMERS = 8
ROUNDS = 50


def _past() -> str:
    return (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)).isoformat()


async def _approved_item(state: StateManager, round_no: int) -> str:
    return await state.add_outbox_item(
        prospect_id=f"p-{round_no}", to_email=f"race-{round_no}@claims.example.test",
        subject="hello there", body="A short, plain note. Question?", send_at=_past(),
        status="approved", campaign_id="camp-race", step=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", BACKENDS)
async def test_concurrent_claimers_on_one_item_yield_exactly_one_claim(backend, tmp_path):
    locator = fresh_locator(backend, tmp_path)
    owner = StateManager(db_path=locator)
    await owner.init_db()
    claimers = [StateManager(db_path=locator) for _ in range(CLAIMERS)]
    for round_no in range(ROUNDS):
        item = await _approved_item(owner, round_no)
        results = await asyncio.gather(*(c.claim_outbox_item(item) for c in claimers))
        assert results.count(True) == 1, f"round {round_no}: {results}"
        assert (await owner.get_outbox_item(item))["status"] == "sending"
        assert await owner.claim_outbox_item(item) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", BACKENDS)
async def test_claimers_in_separate_threads_and_event_loops_yield_one_claim(backend, tmp_path):
    """Like separate processes: each claimer runs its own event loop, released together."""
    locator = fresh_locator(backend, tmp_path)
    owner = StateManager(db_path=locator)
    await owner.init_db()
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=CLAIMERS) as pool:
        for round_no in range(ROUNDS):
            item = await _approved_item(owner, round_no)
            start = threading.Barrier(CLAIMERS)

            def claim(item_id=item, start=start) -> bool:
                start.wait(timeout=30)
                return asyncio.run(StateManager(db_path=locator).claim_outbox_item(item_id))

            results = await asyncio.gather(
                *(loop.run_in_executor(pool, claim) for _ in range(CLAIMERS)))
            assert results.count(True) == 1, f"round {round_no}: {results}"
            assert (await owner.get_outbox_item(item))["status"] == "sending"
