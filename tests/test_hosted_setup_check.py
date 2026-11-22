"""Hosted heartbeat: the setup check in a pod (no .env file) and the
action-log row every cycle writes, which the hosted dashboard reads."""

import asyncio

import pytest

import sellbird.config as config_mod
import sellbird.main as main_mod
from sellbird import paths
from sellbird.auth.config import MODE_ENV
from sellbird.config import SellbirdConfig
from tests.test_send_window import BASE, _patch_heartbeat, state  # noqa: F401 (fixture)

TRAINED = "persona:\n  company: Acme Roofing\n"
UNTRAINED = "persona:\n  company: Your Company\n"


def _home(tmp_path, monkeypatch, config_text, env_file=False):
    home = tmp_path / "home"
    home.mkdir()
    (home / "sellbird.yaml").write_text(config_text, encoding="utf-8")
    if env_file:
        (home / ".env").write_text("X=1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SELLBIRD_HOME", str(home))
    monkeypatch.setattr(config_mod, "PROJECT_ROOT", home)
    monkeypatch.setattr(paths, "PROJECT_ROOT", home)
    return home


def test_gateway_mode_without_env_file_and_trained_config_needs_no_setup(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch, TRAINED)
    monkeypatch.setenv(MODE_ENV, "gateway")
    assert main_mod._needs_setup() is False


def test_gateway_mode_with_template_config_needs_setup(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch, UNTRAINED)
    monkeypatch.setenv(MODE_ENV, "gateway")
    assert main_mod._needs_setup() is True


def test_local_mode_without_env_file_still_needs_setup(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch, TRAINED)
    monkeypatch.delenv(MODE_ENV, raising=False)
    assert main_mod._needs_setup() is True


def test_local_mode_with_env_file_and_trained_config_needs_no_setup(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch, TRAINED, env_file=True)
    monkeypatch.delenv(MODE_ENV, raising=False)
    assert main_mod._needs_setup() is False


# ── every cycle writes a row ──

async def _main_rows(state):
    async with state._connect() as db:
        async with db.execute(
            "SELECT action_type FROM actions WHERE agent = ?", ("main",)
        ) as cursor:
            return [r[0] for r in await cursor.fetchall()]


def _cfg():
    return SellbirdConfig(**BASE, channels={"email": {"provider": "gmail", "send_window": {}}})


@pytest.mark.asyncio
async def test_an_idle_cycle_writes_a_row(state, monkeypatch):  # noqa: F811
    stop = asyncio.Event()
    main_mod_ = _patch_heartbeat(monkeypatch, _cfg(), state, [], stop)
    monkeypatch.setattr(main_mod_, "in_quiet_hours", lambda c: False)

    async def idle(*a, **k):
        return "idle"
    monkeypatch.setattr(main_mod_, "decide_next_action", idle)
    await asyncio.wait_for(main_mod_.heartbeat(stop), timeout=30)
    assert "idle" in await _main_rows(state)
    assert await state.last_heartbeat_at() is not None


@pytest.mark.asyncio
async def test_a_quiet_hours_period_writes_one_row_not_a_flood(state, monkeypatch):  # noqa: F811
    stop = asyncio.Event()
    main_mod_ = _patch_heartbeat(monkeypatch, _cfg(), state, [], stop)  # quiet hours on
    await asyncio.wait_for(main_mod_.heartbeat(stop), timeout=30)
    assert await _main_rows(state) == ["quiet_hours"]


@pytest.mark.asyncio
async def test_a_long_wait_writes_one_row_per_interval(state):  # noqa: F811
    async def never_stops(seconds, event):
        return False
    stop = asyncio.Event()
    import unittest.mock as mock
    with mock.patch.object(main_mod, "_interruptible_sleep", never_stops):
        stopped = await main_mod._sleep_logging(state, 3600, "over_budget", stop, 900)
    assert stopped is False
    assert await _main_rows(state) == ["over_budget"] * 4


# ── hosted, not trained yet: wait instead of exiting ──

@pytest.mark.asyncio
async def test_wait_for_training_returns_true_once_setup_is_done():
    answers = iter([True, True, False])
    sleeps = []

    async def sleep(seconds, event):
        sleeps.append(seconds)
        return False

    done = await main_mod.wait_for_training(
        asyncio.Event(), needs_setup=lambda: next(answers), sleep=sleep)
    assert done is True
    assert sleeps == [main_mod.SETUP_RECHECK_SECONDS] * 3


@pytest.mark.asyncio
async def test_wait_for_training_stops_cleanly_on_a_stop_signal():
    checks = []

    async def sleep(seconds, event):
        return True  # told to stop during the first wait

    done = await main_mod.wait_for_training(
        asyncio.Event(), needs_setup=lambda: checks.append(1) or True, sleep=sleep)
    assert done is False
    assert checks == []


@pytest.mark.asyncio
async def test_wait_for_training_really_wakes_on_the_event(monkeypatch):
    monkeypatch.setattr(main_mod, "SETUP_RECHECK_SECONDS", 3600)
    stop = asyncio.Event()
    task = asyncio.ensure_future(
        main_mod.wait_for_training(stop, needs_setup=lambda: True))
    await asyncio.sleep(0)
    stop.set()
    assert await asyncio.wait_for(task, timeout=5) is False


@pytest.mark.asyncio
async def test_wait_for_training_logs_on_entry_every_fifteen_minutes_and_on_detection(caplog):
    per_log = main_mod.SETUP_REMINDER_SECONDS // main_mod.SETUP_RECHECK_SECONDS
    checks = per_log * 2 + 1  # 31 re-checks still untrained, then trained
    answers = iter([True] * checks + [False])

    async def sleep(seconds, event):
        return False

    with caplog.at_level("INFO", logger=main_mod.logger.name):
        await main_mod.wait_for_training(
            asyncio.Event(), needs_setup=lambda: next(answers), sleep=sleep)
    waiting = [r for r in caplog.records if main_mod.WAITING_FOR_TRAINING_LINE in r.getMessage()]
    detected = [r for r in caplog.records if "Training detected" in r.getMessage()]
    assert len(waiting) == 3  # entry, +15 min, +30 min
    assert len(detected) == 1


@pytest.mark.asyncio
async def test_wait_for_training_survives_a_failing_check():
    calls = iter([RuntimeError("boom"), False])

    def check():
        v = next(calls)
        if isinstance(v, Exception):
            raise v
        return v

    async def sleep(seconds, event):
        return False

    assert await main_mod.wait_for_training(
        asyncio.Event(), needs_setup=check, sleep=sleep) is True


def test_hosted_untrained_main_does_not_exit_and_enters_the_loop_once_trained(monkeypatch):
    monkeypatch.setenv(MODE_ENV, "gateway")
    states = iter([True, False])  # untrained at start, trained after the wait
    monkeypatch.setattr(main_mod, "_needs_setup", lambda: next(states))

    async def fake_wait():
        return True
    monkeypatch.setattr(main_mod, "_wait_phase", fake_wait)
    entered = []

    async def fake_run():
        entered.append(True)
    monkeypatch.setattr(main_mod, "_run_with_signals", fake_run)
    monkeypatch.setattr(main_mod, "hold_loop_lock", lambda p: object())
    monkeypatch.setattr(main_mod, "release_loop_lock", lambda h: None)
    monkeypatch.setattr(main_mod, "write_pid_file", lambda: None)
    monkeypatch.setattr(main_mod, "remove_pid_file", lambda: None)
    main_mod.main()  # must not raise SystemExit
    assert entered == [True]


def test_hosted_untrained_main_returns_without_the_loop_when_stopped(monkeypatch):
    monkeypatch.setenv(MODE_ENV, "gateway")
    monkeypatch.setattr(main_mod, "_needs_setup", lambda: True)

    async def fake_wait():
        return False
    monkeypatch.setattr(main_mod, "_wait_phase", fake_wait)

    async def fake_run():
        raise AssertionError("the loop must not start")
    monkeypatch.setattr(main_mod, "_run_with_signals", fake_run)
    monkeypatch.setattr(main_mod, "hold_loop_lock",
                        lambda p: pytest.fail("the loop lock must not be taken"))
    main_mod.main()


def test_local_mode_untrained_without_a_tty_still_exits_1(monkeypatch, capsys):
    monkeypatch.delenv(MODE_ENV, raising=False)
    monkeypatch.setattr(main_mod, "_needs_setup", lambda: True)
    monkeypatch.setattr(main_mod.sys.stdin, "isatty", lambda: False, raising=False)
    with pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == 1
    assert "isn't set up yet" in capsys.readouterr().out
