"""How the dashboard page authorises its API calls in each mode.

Local mode: the dashboard token from the link, as an Authorization header, and
no cookies. Gateway mode: the operator signed in at the gateway, so the page
sends this origin's cookies and no Authorization header (the gateway adds its
own), and never stores or asks for a dashboard token. The server tells the
page which mode it is in with a <meta> tag on the shell.

The browser side runs under node with stand-ins for window, document,
sessionStorage and fetch. Hosts are example.test placeholders.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import sellbird.dashboard as dash
from sellbird.auth import config as gwconfig

WEB = Path(dash.__file__).resolve().parent / "web"
PUBLIC_HOST = "sellbird.example.test"
ORIGIN = f"https://{PUBLIC_HOST}"
TOKEN = "T" * 43

GATEWAY_ENV = {
    gwconfig.MODE_ENV: "gateway",
    gwconfig.PUBLIC_HOST_ENV: PUBLIC_HOST,
    gwconfig.ISSUER_ENV: "https://gate.example.test",
    gwconfig.AUDIENCE_ENV: "sellbird",
    gwconfig.JWKS_URL_ENV: "http://flint-gate.flint-gate.svc.cluster.local:4456/.well-known/jwks.json",
    gwconfig.ALLOWED_SUBS_ENV: "0000000a-0000-4000-8000-00000000000b",
}


# ── The server marks the mode on the shell ──


async def _no_jwks(url: str) -> bytes:
    pytest.fail("the public shell must not need the gateway's keys")


def test_gateway_shell_says_it_is_in_gateway_mode():
    app = dash.build_gateway_app(gwconfig.load_gateway_config(GATEWAY_ENV), fetch=_no_jwks)
    with TestClient(app, base_url=ORIGIN) as client:
        html = client.get("/").text
    assert dash.GATEWAY_MODE_META in html
    # Before auth.js, which reads it as it loads.
    assert html.index(dash.GATEWAY_MODE_META) < html.index("/static/auth.js")


def test_local_shell_does_not_claim_gateway_mode():
    with TestClient(dash.app, base_url="http://127.0.0.1:5555") as client:
        html = client.get("/").text
    assert "sellbird-dashboard-mode" not in html


def test_a_gateway_app_does_not_change_the_local_shell():
    dash.build_gateway_app(gwconfig.load_gateway_config(GATEWAY_ENV), fetch=_no_jwks)
    with TestClient(dash.app, base_url="http://127.0.0.1:5555") as client:
        assert "sellbird-dashboard-mode" not in client.get("/").text


def test_the_token_form_can_be_hidden_as_one_block():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    block = html[html.index('id="lock-token-help"'):html.index('<div class="app">')]
    assert 'id="lock-token"' in block and "data/dashboard-token" in block
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert "getElementById('lock-token-help')" in app


# ── The page, under node ──

NODE_HARNESS = r"""
const [file, mode, hash, origin] = process.argv.slice(1);
const store = {};
const calls = [];
globalThis.window = {location: {origin, pathname: '/', search: '', hash: hash || ''}};
globalThis.location = window.location;
globalThis.history = {replaceState: () => { window.location.hash = ''; }};
globalThis.document = {querySelector: sel =>
  (mode === 'gateway' && sel === 'meta[name="sellbird-dashboard-mode"]')
    ? {getAttribute: name => (name === 'content' ? 'gateway' : null)} : null};
globalThis.sessionStorage = {getItem: k => (k in store ? store[k] : null),
                             setItem: (k, v) => { store[k] = String(v); },
                             removeItem: k => { delete store[k]; }};
globalThis.fetch = (url, opts) => { calls.push({url, opts}); return Promise.resolve({}); };
eval(require('fs').readFileSync(file, 'utf8') +
     ';globalThis.T = {authFetch, authToken, setAuthToken, gatewayMode};');
(async () => {
  const out = {gateway: T.gatewayMode(), hashAfter: window.location.hash,
               storedFromLink: Object.keys(store).length,
               pasted: T.setAuthToken('P'.repeat(43)), token: T.authToken()};
  await T.authFetch('/api/companies', {method: 'POST',
    headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer from-the-caller'}});
  out.offOrigin = await T.authFetch('https://evil.example/api').then(() => 'sent', () => 'refused');
  const c = calls[calls.length - 1];
  out.calls = calls.length;
  out.call = {url: c.url, auth: c.opts.headers.get('authorization'),
              ctype: c.opts.headers.get('content-type'), mode: c.opts.mode,
              credentials: c.opts.credentials, redirect: c.opts.redirect,
              cache: c.opts.cache, referrerPolicy: c.opts.referrerPolicy};
  process.stdout.write(JSON.stringify(out));
})();
"""


def _page(mode: str, hash_value: str = "", origin: str = ORIGIN) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run(
        [node, "-e", NODE_HARNESS, str(WEB / "auth.js"), mode, hash_value, origin],
        capture_output=True, text=True, check=True, timeout=30)
    return json.loads(out.stdout)


def test_gateway_mode_sends_the_sign_in_cookie_and_no_token():
    out = _page("gateway")
    assert out["gateway"] is True
    call = out["call"]
    assert call["credentials"] == "same-origin"
    assert call["auth"] is None  # the gateway writes Authorization, never the page
    assert call["url"] == f"{ORIGIN}/api/companies"
    assert call["ctype"] == "application/json"
    assert call["mode"] == "same-origin" and call["redirect"] == "error"
    assert call["cache"] == "no-store" and call["referrerPolicy"] == "same-origin"


def test_gateway_mode_never_stores_a_dashboard_token():
    out = _page("gateway", f"#token={TOKEN}")
    assert out["hashAfter"] == ""          # still taken out of the address bar
    assert out["storedFromLink"] == 0      # but not kept
    assert out["pasted"] is False and out["token"] == ""
    assert out["call"]["auth"] is None


def test_gateway_mode_still_refuses_other_origins():
    out = _page("gateway")
    assert out["offOrigin"] == "refused"
    assert out["calls"] == 1


def test_local_mode_is_unchanged_token_only_and_no_cookies():
    out = _page("local", f"#token={TOKEN}", origin="http://127.0.0.1:5555")
    assert out["gateway"] is False
    assert out["storedFromLink"] == 1 and out["hashAfter"] == ""
    assert out["pasted"] is True
    call = out["call"]
    assert call["credentials"] == "omit"
    assert call["auth"] == "Bearer " + "P" * 43  # the page's token replaces a caller's header
    assert call["mode"] == "same-origin" and call["redirect"] == "error"
    assert out["offOrigin"] == "refused" and out["calls"] == 1
