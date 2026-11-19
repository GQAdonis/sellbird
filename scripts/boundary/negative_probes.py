#!/usr/bin/env python3
"""Probes behind scripts/boundary/negative_controls.sh (never run on their own).

Each ``probe`` plants one bad input, observes the system, and ends with one
line ``PROBE PASS|FAIL|BLOCKED: <reason>`` and exit status 0, 1 or 2. A control
PASSES only when the expected refusal is seen; a refusal for another reason is
a FAIL. Postgres cases read two connection strings from
SELLBIRD_TEST_PG_MIGRATE_DSN and SELLBIRD_TEST_PG_APP_DSN (the local stand-in's,
from scripts/local/dsn.sh) and never print them.

    negative_probes.py copy-tree <repo> <dest>     working-tree copy without agent folders
    negative_probes.py plant <dedup|log> <tree>    plant a defect in a scratch tree
    negative_probes.py store002|store003|send001|move001|auth002   run a probe
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_PREFIXES = (".git/", ".claude/", ".agent-team/", ".kbd-orchestrator/", ".codex/",
                 ".opencode/", ".qwen/", ".kimi-code/", ".impeccable/", ".venv/", "data/")
PG_ENV = ("SELLBIRD_TEST_PG_MIGRATE_DSN", "SELLBIRD_TEST_PG_APP_DSN")


class Blocked(Exception):
    """A prerequisite is missing: the control could not run."""


class Failed(Exception):
    """The bad input was accepted, or was refused for the wrong reason."""


def mask(text: str) -> str:
    return re.sub(r"postgres(ql)?://\S+", "postgresql://***", text)


# ── scratch trees and planted defects ──

def copy_tree(repo: Path, dest: Path) -> None:
    listing = subprocess.run(["git", "-C", str(repo), "ls-files", "-co", "--exclude-standard", "-z"],
                             capture_output=True, check=True).stdout.decode()
    for rel in filter(None, listing.split("\0")):
        src = repo / rel
        if rel.startswith(SKIP_PREFIXES) or src.is_dir() or not src.exists():
            continue
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / rel, follow_symlinks=False)


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise Blocked(f"cannot plant: expected one occurrence in {path.name}, found {text.count(old)}")
    path.write_text(text.replace(old, new), encoding="utf-8")


PLANTS = {
    # Company dedup stops normalising the domain: " Bakery.Example.test" and
    # "bakery.example.test" become two companies.
    # Both layers normalise (the Company model's validator and add_company),
    # so both are planted; either alone would still dedup.
    "dedup": (("sellbird/state.py", "company.domain = _norm(company.domain)",
               "company.domain = company.domain or \"\""),
              ("sellbird/models/company.py", 'return (v or "").strip().lower()',
               'return v or ""')),
    # The container guard that withholds the unlock link from logs is removed.
    "log": (("sellbird/dashboard.py",
             "    if running_in_container():\n        # Container logs",
             "    if False:  # planted: token printing re-enabled\n        # Container logs"),),
}


# ── backends ──

def pg_ready() -> None:
    if not all(os.environ.get(name) for name in PG_ENV):
        raise Blocked("Postgres stand-in DSNs are not set (scripts/local/dsn.sh)")
    try:
        import psycopg
        with psycopg.connect(os.environ[PG_ENV[1]], connect_timeout=5):
            pass
    except Exception as exc:  # noqa: BLE001 - any failure to reach it means blocked
        raise Blocked(f"Postgres stand-in not reachable ({type(exc).__name__})") from None


def locators(tmp: Path) -> list[tuple[str, str]]:
    from tests.storage_contract.backends import fresh_locator

    pg_ready()
    return [("sqlite", fresh_locator("sqlite", tmp)), ("postgres", fresh_locator("postgres", tmp))]


# ── probes ──

async def _store002(locator: str, backend: str) -> None:
    from sellbird.state import StateManager

    state = StateManager(db_path=locator)
    await state.init_db()
    for label, call in (
        ("single", lambda: state.add_observation("NOT_A_SIGNAL", company_id="co-1", value_num=1)),
        ("batch", lambda: state.add_observations(
            [{"signal_code": "ALSO_NOT_A_SIGNAL", "company_id": "co-1"}])),
    ):
        try:
            await call()
        except sqlite3.IntegrityError as exc:
            if "unknown signal_code" not in str(exc):
                raise Failed(f"{backend} {label}: refused for another reason: {exc}") from None
        except Exception as exc:  # noqa: BLE001
            raise Failed(f"{backend} {label}: wrong failure {type(exc).__name__}") from None
        else:
            raise Failed(f"{backend} {label}: an unknown signal code was accepted")
    fresh = StateManager(db_path=locator)  # a second connection: nothing was committed
    if await fresh.get_observations() or await state.get_observations():
        raise Failed(f"{backend}: a row exists after the refused write")


def store002() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        for backend, locator in locators(Path(tmp)):
            asyncio.run(_store002(locator, backend))
    return "unknown signal code refused with 'unknown signal_code' and no row, on sqlite and postgres"


def store003() -> str:
    import psycopg
    from tests.storage_contract.backends import fresh_pg_locator

    pg_ready()
    app_dsn = fresh_pg_locator()  # newest schema, tables empty
    statements = {
        "CREATE TABLE": "CREATE TABLE negctl_probe (id integer)",
        "ALTER TABLE": "ALTER TABLE companies ADD COLUMN negctl_probe integer",
    }
    with psycopg.connect(app_dsn, autocommit=True, connect_timeout=5) as conn:
        who = conn.execute("SELECT current_user").fetchone()[0]
        if who != "sellbird_app":
            raise Blocked(f"runtime DSN connects as {who!r}, not sellbird_app")
        for label, statement in statements.items():
            try:
                conn.execute(statement)
            except psycopg.Error as exc:
                if getattr(exc, "sqlstate", None) != "42501":
                    raise Failed(f"{label} refused with SQLSTATE {exc.sqlstate}, not 42501") from None
            else:
                raise Failed(f"{label} was accepted for the runtime role")
        leftovers = conn.execute(
            "SELECT to_regclass('public.negctl_probe'), (SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'companies' AND column_name = 'negctl_probe')").fetchone()
        if leftovers[0] is not None or leftovers[1]:
            raise Failed("a planted table or column exists after the refusals")
    return "CREATE TABLE and ALTER TABLE both refused with SQLSTATE 42501 as sellbird_app"


async def _send001(locator: str, backend: str) -> None:
    from datetime import datetime, timedelta, timezone

    from sellbird.state import StateManager

    owner = StateManager(db_path=locator)
    await owner.init_db()
    past = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)).isoformat()

    async def approved(n: int) -> str:
        return await owner.add_outbox_item(
            prospect_id=f"p-{n}", to_email=f"race-{n}@claims.example.test", subject="hello there",
            body="A short, plain note. Question?", send_at=past, status="approved",
            campaign_id="camp-negctl", step=1)

    item = await approved(0)
    if await StateManager(db_path=locator).claim_outbox_item(item) is not True:
        raise Failed(f"{backend}: the first claimer got no claim")
    if await StateManager(db_path=locator).claim_outbox_item(item) is not False:
        raise Failed(f"{backend}: a second claimer was given an already-claimed item")
    if (await owner.get_outbox_item(item))["status"] != "sending":
        raise Failed(f"{backend}: the claimed item is not 'sending'")
    racers = [StateManager(db_path=locator) for _ in range(8)]
    item = await approved(1)
    wins = (await asyncio.gather(*(r.claim_outbox_item(item) for r in racers))).count(True)
    if wins != 1:
        raise Failed(f"{backend}: {wins} of 8 simultaneous claimers won")


def send001() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        for backend, locator in locators(Path(tmp)):
            asyncio.run(_send001(locator, backend))
    return "a second claimer gets no claim, and 8 racers yield exactly one, on sqlite and postgres"


def move001() -> str:
    import psycopg
    from sellbird.storage_postgres import move
    from tests.storage_contract.backends import fresh_pg_locator

    pg_ready()
    target = fresh_pg_locator()
    with tempfile.TemporaryDirectory() as tmp:
        spec = importlib.util.spec_from_file_location(
            "negctl_move_fixture", ROOT / "tests" / "fixtures" / "move" / "build_fixture.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        source = builder.build(Path(tmp) / "sellbird.db")

        def snapshot() -> dict[str, tuple[int, str]]:
            with psycopg.connect(target, autocommit=True, connect_timeout=5) as conn:
                out = {}
                for name in move.TABLES:
                    count = conn.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
                    digest = conn.execute(
                        f'SELECT coalesce(md5(string_agg(t::text, \'|\' ORDER BY t::text)), \'\') '
                        f'FROM "{name}" t').fetchone()[0]
                    out[name] = (count, digest)
                return out

        with psycopg.connect(target, autocommit=True, connect_timeout=5) as conn:
            conn.execute("INSERT INTO settings (key, value, updated_at) "
                         "VALUES ('sending_paused', '1', '2026-03-01T00:00:00')")
        before = snapshot()
        env = {**os.environ, "NEGCTL_MOVE_TARGET": target, "SELLBIRD_HOME": tmp,
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT)}
        done = subprocess.run(
            [sys.executable, "-m", "sellbird", "storage", "move", "--from", str(source),
             "--to-env", "NEGCTL_MOVE_TARGET"],
            cwd=tmp, env=env, capture_output=True, text=True, timeout=120)
        output = done.stdout + done.stderr
        password = re.search(r"//[^:]+:([^@]+)@", target)
        if password and password.group(1) in output:
            raise Failed("the move output contains the connection password")
        if done.returncode == 0:
            raise Failed("the move succeeded into a target that already held rows")
        if "already holds Sellbird rows" not in output or "settings" not in output:
            raise Failed(f"refused for another reason: {mask(output.strip())[-300:]}")
        if snapshot() != before:
            raise Failed("the target changed although the move was refused")
    return "move refused with 'already holds Sellbird rows (in settings)'; every table unchanged"


def auth002() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("SELLBIRD_GATE", "SELLBIRD_PUBLIC", "SELLBIRD_DATABASE",
                                    "SELLBIRD_MIGRATE", "SELLBIRD_DASHBOARD"))}
        env.update({"SELLBIRD_HOME": tmp, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT)})
        env.pop("KUBERNETES_SERVICE_HOST", None)
        try:
            done = subprocess.run(
                [sys.executable, "-m", "sellbird", "dashboard", "--host", "0.0.0.0", "--port", "5599"],
                cwd=tmp, env=env, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise Failed("the dashboard kept running on 0.0.0.0 (no refusal within 60s)") from None
    output = done.stdout + done.stderr
    if done.returncode != 2 or "only listens on this machine" not in output:
        raise Failed(f"exit {done.returncode}, no loopback refusal: {output.strip()[-300:]}")
    if "#token=" in output:
        raise Failed("the refusal output carries an unlock link")
    return "start on 0.0.0.0 exited 2 with the loopback refusal and printed no link"


PROBES = {"store002": store002, "store003": store003, "send001": send001,
          "move001": move001, "auth002": auth002}


def main(argv: list[str]) -> int:
    if argv[:1] == ["copy-tree"] and len(argv) == 3:
        copy_tree(Path(argv[1]), Path(argv[2]))
        return 0
    if argv[:1] == ["plant"] and len(argv) == 3 and argv[1] in PLANTS:
        try:
            for rel, old, new in PLANTS[argv[1]]:
                replace_once(Path(argv[2]) / rel, old, new)
        except Blocked as exc:
            print(f"PROBE BLOCKED: {exc}")
            return 2
        return 0
    if len(argv) != 1 or argv[0] not in PROBES:
        print(__doc__, file=sys.stderr)
        return 64
    sys.path.insert(0, str(ROOT))
    try:
        reason = PROBES[argv[0]]()
    except Blocked as exc:
        print(f"PROBE BLOCKED: {mask(str(exc))}")
        return 2
    except Failed as exc:
        print(f"PROBE FAIL: {mask(str(exc))}")
        return 1
    except ImportError as exc:
        print(f"PROBE BLOCKED: missing dependency ({exc.name})")
        return 2
    print(f"PROBE PASS: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
