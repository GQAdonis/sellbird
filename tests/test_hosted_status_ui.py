"""What the dashboard's Agent card shows in each mode.

Local mode keeps its start/stop controls. Hosted (gateway) mode has none: the
loop runs elsewhere, so the card says whether it is running and when it last
completed a cycle. The mapping is a pure function in app.js, evaluated here
under node on its own with stand-in formatters. Times are fictional.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import sellbird.dashboard as dash

WEB = Path(dash.__file__).resolve().parent / "web"

HARNESS = r"""
const src = require('fs').readFileSync(process.argv[1], 'utf8');
const m = src.match(/function hostedStatusView[\s\S]*?\n}\n/);
eval(m[0] + ';globalThis.V = hostedStatusView;');
const ago = t => 'AGO(' + t + ')', abs = t => 'ABS(' + t + ')';
const cases = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(cases.map(c => V(c.data, c.fallback, ago, abs))));
"""


def _view(cases: list[dict]) -> list[dict]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, "-e", HARNESS, str(WEB / "app.js"), json.dumps(cases)],
                         capture_output=True, text=True, check=True, timeout=30)
    return json.loads(out.stdout)


LAST = "2026-01-02T03:04:05+00:00"


def test_local_status_is_left_to_the_existing_controls():
    local = {"running": True, "pid": 7, "started_at": "x", "sending_paused": "", "mode": "local"}
    assert _view([{"data": local, "fallback": False}]) == [{"hosted": False}]


def test_hosted_running_shows_last_cycle_and_no_controls():
    data = {"running": True, "pid": None, "started_at": None, "mode": "gateway",
            "last_cycle_at": LAST, "stale_after_seconds": 2700}
    [v] = _view([{"data": data, "fallback": False}])
    assert v["hosted"] and v["running"] and v["showControls"] is False
    assert v["label"] == "Running" and v["detail"] == f"Last cycle: AGO({LAST})"
    assert v["title"] == f"ABS({LAST})" and v["note"] == ""


def test_hosted_stale_says_not_running_and_who_starts_it():
    data = {"running": False, "mode": "gateway", "last_cycle_at": LAST, "stale_after_seconds": 2700}
    [v] = _view([{"data": data, "fallback": False}])
    assert v["label"] == "Not running" and v["showControls"] is False
    assert "started by the platform" in v["note"] and v["detail"].startswith("Last cycle:")


def test_hosted_never_run_says_no_cycle_recorded():
    data = {"running": False, "mode": "gateway", "last_cycle_at": None, "stale_after_seconds": 2700}
    [v] = _view([{"data": data, "fallback": False}])
    assert v["detail"] == "No cycle recorded yet" and v["title"] == ""


def test_a_missing_mode_field_falls_back_to_the_page_mode():
    data = {"running": False}
    hosted, local = _view([{"data": data, "fallback": True}, {"data": data, "fallback": False}])
    assert hosted["hosted"] is True and local["hosted"] is False


def test_hosted_status_never_calls_start_or_stop():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    for name in ("startSellbird", "stopSellbird"):
        body = app[app.index(f"async function {name}()"):]
        assert re.match(r"[^\n]*\n\s*if \(gatewayMode\(\)\) return;", body)
