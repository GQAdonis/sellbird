"""Gateway mode and local token mode, in process (sellbird/auth, dashboard startup).

Covers openspec/changes/hosted-gateway-mode (SCN-AUTH-002 and the in-process
half of SCN-AUTH-001): local mode still refuses public binds and ignores
gateway headers; gateway mode is chosen only by configuration, admits only a
valid flint-gate token for an allowlisted Kratos identity (principal ``user``)
and refuses everything else with 401 and no data; the dashboard token is
never printed in gateway mode or in a container.

Every key is generated here at run time and thrown away; nothing secret is
stored in the repository. Identities, hosts and issuers are example.test
placeholders.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

import sellbird.dashboard as dash
from sellbird.auth import config as gwconfig
from sellbird.auth import jwks as gwjwks
from sellbird.auth.gate_token import GateTokenError, GateTokenVerifier

PUBLIC_HOST = "sellbird.example.test"
ORIGIN = f"https://{PUBLIC_HOST}"
ISSUER = "https://gate.example.test"
AUDIENCE = "sellbird"
JWKS_URL = "http://flint-gate.flint-gate.svc.cluster.local:4456/.well-known/jwks.json"
ALLOWED_SUB = "00000000-0000-4000-8000-000000000001"
OTHER_SUB = "00000000-0000-4000-8000-000000000002"
KID = "test-key-1"

GATEWAY_ENV = {
    gwconfig.MODE_ENV: "gateway",
    gwconfig.PUBLIC_HOST_ENV: PUBLIC_HOST,
    gwconfig.ISSUER_ENV: ISSUER,
    gwconfig.AUDIENCE_ENV: AUDIENCE,
    gwconfig.JWKS_URL_ENV: JWKS_URL,
    gwconfig.ALLOWED_SUBS_ENV: ALLOWED_SUB,
}
ALL_MODE_ENV = [*GATEWAY_ENV, gwconfig.CONTAINER_ENV, "KUBERNETES_SERVICE_HOST", "container"]


# ── Keys and tokens (generated per test session, never stored) ──


def _rsa_key(bits: int = 2048):
    return rsa.generate_private_key(public_exponent=65537, key_size=bits)


@pytest.fixture(scope="module")
def gate_key():
    return _rsa_key()


@pytest.fixture(scope="module")
def attacker_key():
    return _rsa_key()


def _jwk(private_key, kid: str = KID) -> dict:
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    return {**jwk, "kid": kid, "use": "sig", "alg": "RS256"}


def _jwks_bytes(*jwks: dict) -> bytes:
    return json.dumps({"keys": list(jwks)}).encode()


def _claims(**overrides) -> dict:
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": ALLOWED_SUB, "iat": now,
              "exp": now + 300, "jti": "11111111-1111-4111-8111-111111111111",
              "aal": "aal2", "email": "operator@example.test"}
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def _token(private_key, *, kid: str | None = KID, headers: dict | None = None, **claims) -> str:
    extra = dict(headers or {})
    if kid is not None:
        extra["kid"] = kid
    return jwt.encode(_claims(**claims), private_key, algorithm="RS256", headers=extra)


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


# ── Fixtures ──


@pytest.fixture
def clean_env(monkeypatch):
    for name in ALL_MODE_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def gateway_env(clean_env):
    for name, value in GATEWAY_ENV.items():
        clean_env.setenv(name, value)
    return clean_env


@pytest.fixture
def no_server(monkeypatch):
    import uvicorn
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: pytest.fail("must not start"))


@pytest.fixture
def config():
    return gwconfig.load_gateway_config(GATEWAY_ENV)


class FakeJwks:
    """The JWKS download, replaced: counts fetches, can fail."""

    def __init__(self, body: bytes):
        self.body = body
        self.calls = 0
        self.fail = False

    async def __call__(self, url: str) -> bytes:
        assert url == JWKS_URL  # only ever the pinned URL
        self.calls += 1
        if self.fail:
            raise gwjwks.JwksError("unreachable")
        return self.body


@pytest.fixture
def fake_jwks(gate_key):
    return FakeJwks(_jwks_bytes(_jwk(gate_key)))


@pytest.fixture
def gw(clean_env, config, fake_jwks):
    """A gateway-mode app, reached at the public host over https."""
    app = dash.build_gateway_app(config, fetch=fake_jwks)
    with TestClient(app, base_url=ORIGIN) as client:
        yield client


@pytest.fixture
def local(clean_env, tmp_path):
    """The local (token-guarded) app; the agent token lives in tmp_path too."""
    dash.agent_token_store.configure(tmp_path / "agent-token")
    try:
        with TestClient(dash.app, base_url="http://127.0.0.1:5555") as client:
            yield client
    finally:
        dash.agent_token_store.configure(dash.AGENT_TOKEN_FILE)


def _assert_refused(response):
    assert response.status_code == 401
    assert response.content == b""
    assert response.headers.get("www-authenticate") == 'Bearer realm="sellbird"'


# ── Mode selection and binding (SCN-AUTH-002) ──


def test_local_is_the_default_mode(clean_env):
    assert gwconfig.dashboard_mode() == "local"
    assert gwconfig.dashboard_mode({gwconfig.MODE_ENV: "local"}) == "local"


@pytest.mark.parametrize("value", ["Gateway", "GATEWAY", "hosted", "gateway ", "1", "true"])
def test_unknown_mode_values_are_refused(clean_env, no_server, value):
    clean_env.setenv(gwconfig.MODE_ENV, value)
    if value.strip() == "gateway":  # surrounding whitespace is trimmed, not a new mode
        assert gwconfig.dashboard_mode() == "gateway"
        return
    with pytest.raises(dash.DashboardSetupError, match="SELLBIRD_DASHBOARD_MODE"):
        dash.start_dashboard(host="127.0.0.1", port=5555)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "example.test"])
def test_local_mode_refuses_public_binds(clean_env, no_server, host):
    with pytest.raises(dash.DashboardSetupError, match="only listens on this machine"):
        dash.start_dashboard(host=host, port=5555)


def test_local_mode_refusal_through_the_cli(clean_env, no_server, capsys):
    import sellbird.cli as cli
    args = type("A", (), {"host": "0.0.0.0", "port": 5555, "url": False})()
    with pytest.raises(SystemExit) as e:
        cli.cmd_dashboard(args)
    assert e.value.code == 2
    assert "only listens on this machine" in capsys.readouterr().out


def test_gateway_settings_alone_do_not_open_local_mode(clean_env, no_server):
    """Every gateway key except the mode switch: still local, still refused."""
    for name, value in GATEWAY_ENV.items():
        if name != gwconfig.MODE_ENV:
            clean_env.setenv(name, value)
    with pytest.raises(dash.DashboardSetupError, match="only listens on this machine"):
        dash.start_dashboard(host="0.0.0.0", port=5555)


def test_gateway_mode_binds_publicly_and_prints_no_token(gateway_env, monkeypatch, capsys):
    import uvicorn
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **k: calls.append((app, k)))
    dash.start_dashboard(host="0.0.0.0", port=5555)
    app, kwargs = calls[0]
    assert app is not dash.app  # the gateway-guarded app, not the token-guarded one
    assert kwargs["host"] == "0.0.0.0" and kwargs["port"] == 5555
    assert kwargs["proxy_headers"] is False and kwargs["log_level"] == "warning"
    out = capsys.readouterr().out
    assert "token" not in out.lower()
    assert "#" not in out
    assert not dash.token_store.path.exists()  # never even created


@pytest.mark.parametrize("missing", [k for k in GATEWAY_ENV if k != gwconfig.MODE_ENV])
def test_gateway_mode_needs_every_setting(gateway_env, no_server, missing):
    gateway_env.delenv(missing)
    with pytest.raises(dash.DashboardSetupError, match=missing):
        dash.start_dashboard(host="0.0.0.0", port=5555)


@pytest.mark.parametrize("name, value", [
    (gwconfig.PUBLIC_HOST_ENV, "https://sellbird.example.test"),
    (gwconfig.PUBLIC_HOST_ENV, "sellbird.example.test/path"),
    (gwconfig.JWKS_URL_ENV, "file:///etc/jwks.json"),
    (gwconfig.JWKS_URL_ENV, "http://user:pw@gate.example.test/jwks"),
    (gwconfig.ALLOWED_SUBS_ENV, "operator@example.test"),
    (gwconfig.ALLOWED_SUBS_ENV, " , "),
])
def test_invalid_gateway_settings_are_refused(gateway_env, no_server, name, value):
    gateway_env.setenv(name, value)
    with pytest.raises(dash.DashboardSetupError):
        dash.start_dashboard(host="0.0.0.0", port=5555)


def test_gateway_bind_must_be_an_address(gateway_env, no_server):
    with pytest.raises(dash.DashboardSetupError, match="IP address"):
        dash.start_dashboard(host="sellbird.example.test", port=5555)


def test_cli_url_is_refused_in_gateway_mode(gateway_env, no_server, capsys):
    import sellbird.cli as cli
    args = type("A", (), {"host": "127.0.0.1", "port": 5555, "url": True})()
    with pytest.raises(SystemExit) as e:
        cli.cmd_dashboard(args)
    assert e.value.code == 2
    out = capsys.readouterr().out
    assert "#token=" not in out
    assert not dash.token_store.path.exists()


# ── Token never printed in a container (SCN-LOG-001, in process) ──


@pytest.mark.parametrize("signal", [(gwconfig.CONTAINER_ENV, "1"),
                                    ("KUBERNETES_SERVICE_HOST", "10.0.0.1")])
def test_local_mode_in_a_container_prints_no_token(clean_env, monkeypatch, capsys, signal):
    import uvicorn
    clean_env.setenv(*signal)
    monkeypatch.setattr(uvicorn, "run", lambda app, **k: None)
    monkeypatch.setattr(dash, "DB_PATH", dash.token_store.path.parent / "sellbird.db")
    dash.start_dashboard(host="127.0.0.1", port=5555)
    out = capsys.readouterr().out
    assert dash.token_store.get() not in out
    assert "#token=" not in out


def test_cli_url_is_refused_in_a_container(clean_env, no_server, capsys):
    import sellbird.cli as cli
    clean_env.setenv(gwconfig.CONTAINER_ENV, "1")
    args = type("A", (), {"host": "127.0.0.1", "port": 5555, "url": True})()
    with pytest.raises(SystemExit) as e:
        cli.cmd_dashboard(args)
    assert e.value.code == 2
    assert "#token=" not in capsys.readouterr().out


def test_container_detection_ignores_a_plain_machine():
    assert gwconfig.running_in_container({}) is False
    assert gwconfig.running_in_container({gwconfig.CONTAINER_ENV: "0"}) is False


# ── Headers cannot switch modes (SCN-AUTH-002) ──


def test_gateway_identity_headers_are_ignored_in_local_mode(local, gate_key):
    headers = {
        "Authorization": f"Bearer {_token(gate_key)}",  # a valid gate token, wrong mode
        "x-flint-user-id": ALLOWED_SUB,
        "x-flint-auth-method": "kratos_session",
        "X-Forwarded-Host": PUBLIC_HOST,
        "X-Forwarded-Proto": "https",
        "Forwarded": f"host={PUBLIC_HOST};proto=https",
        "SELLBIRD_DASHBOARD_MODE": "gateway",
        "X-Sellbird-Dashboard-Mode": "gateway",
        "Cookie": "ory_kratos_session=example-session-value",
    }
    r = local.get("/api/stats", headers=headers)
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"  # the local guard answered
    assert local.get("/api/auth/whoami", headers=headers).status_code == 401


def test_gateway_public_host_is_refused_in_local_mode(clean_env, gate_key):
    with TestClient(dash.app, base_url=ORIGIN) as client:
        r = client.get("/api/stats", headers={"Authorization": f"Bearer {_token(gate_key)}"})
    assert r.status_code == 400 and r.json()["error"] == "bad_host"


# ── Gateway mode: who gets in (SCN-AUTH-001, in process) ──


def test_allowlisted_identity_is_admitted_as_user(gw, gate_key):
    r = gw.get("/api/auth/whoami", headers={"Authorization": f"Bearer {_token(gate_key)}"})
    assert r.status_code == 200
    assert r.json() == {"mode": "gateway", "principal": "user", "sub": ALLOWED_SUB}


def test_no_token_is_refused(gw):
    _assert_refused(gw.get("/api/auth/whoami"))
    _assert_refused(gw.get("/api/stats"))


def test_forged_identity_header_without_a_token_is_refused(gw):
    _assert_refused(gw.get("/api/stats", headers={
        "x-flint-user-id": ALLOWED_SUB, "x-flint-identity-id": ALLOWED_SUB,
        "x-flint-auth-method": "kratos_session", "X-Forwarded-User": ALLOWED_SUB}))


def test_cookie_alone_is_refused(gw):
    _assert_refused(gw.get("/api/stats",
                           headers={"Cookie": "ory_kratos_session=example-session-value"}))


def test_wrong_audience_is_refused(gw, gate_key):
    for aud in ("flint", ["sellbird", "flint"], ["sellbird"]):
        _assert_refused(gw.get("/api/stats",
                               headers={"Authorization": f"Bearer {_token(gate_key, aud=aud)}"}))


def test_expired_token_is_refused(gw, gate_key):
    now = int(time.time())
    token = _token(gate_key, iat=now - 400, exp=now - 100)
    _assert_refused(gw.get("/api/stats", headers={"Authorization": f"Bearer {token}"}))


def test_non_allowlisted_identity_is_refused(gw, gate_key):
    token = _token(gate_key, sub=OTHER_SUB)
    _assert_refused(gw.get("/api/stats", headers={"Authorization": f"Bearer {token}"}))


@pytest.mark.parametrize("case", [
    "wrong_issuer", "missing_exp", "missing_iat", "missing_sub", "lifetime_too_long",
    "issued_in_future", "not_yet_valid", "aal1", "sub_not_uuid", "sub_uppercase",
    "missing_kid", "unknown_kid", "jku_header", "x5u_header", "jwk_header",
])
def test_other_bad_tokens_are_refused(gw, gate_key, case):
    now = int(time.time())
    token = {
        "wrong_issuer": lambda: _token(gate_key, iss="https://other.example.test"),
        "missing_exp": lambda: _token(gate_key, exp=None),
        "missing_iat": lambda: _token(gate_key, iat=None),
        "missing_sub": lambda: _token(gate_key, sub=None),
        "lifetime_too_long": lambda: _token(gate_key, iat=now, exp=now + 3600),
        "issued_in_future": lambda: _token(gate_key, iat=now + 120, exp=now + 300),
        "not_yet_valid": lambda: _token(gate_key, nbf=now + 120),
        "aal1": lambda: _token(gate_key, aal="aal1"),
        "sub_not_uuid": lambda: _token(gate_key, sub="operator"),
        "sub_uppercase": lambda: _token(gate_key, sub=ALLOWED_SUB.upper()),
        "missing_kid": lambda: _token(gate_key, kid=None),
        "unknown_kid": lambda: _token(gate_key, kid="no-such-key"),
        "jku_header": lambda: _token(gate_key, headers={"jku": "https://evil.example.test/jwks"}),
        "x5u_header": lambda: _token(gate_key, headers={"x5u": "https://evil.example.test/x5u"}),
        "jwk_header": lambda: _token(gate_key, headers={"jwk": _jwk(gate_key)}),
    }[case]()
    _assert_refused(gw.get("/api/stats", headers={"Authorization": f"Bearer {token}"}))


def test_token_signed_by_another_key_with_the_gate_kid_is_refused(gw, attacker_key):
    _assert_refused(gw.get("/api/stats",
                           headers={"Authorization": f"Bearer {_token(attacker_key)}"}))


def test_algorithm_confusion_and_none_are_refused(gw, gate_key):
    public_pem = gate_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    header = {"alg": "HS256", "kid": KID, "typ": "JWT"}
    signing_input = f"{_b64(header)}.{_b64(_claims())}".encode()
    import hashlib
    import hmac
    sig = base64.urlsafe_b64encode(
        hmac.new(public_pem, signing_input, hashlib.sha256).digest()).rstrip(b"=").decode()
    hs256 = f"{signing_input.decode()}.{sig}"
    unsigned = f"{_b64({'alg': 'none', 'kid': KID})}.{_b64(_claims())}."
    for token in (hs256, unsigned):
        _assert_refused(gw.get("/api/stats", headers={"Authorization": f"Bearer {token}"}))


def test_malformed_authorization_is_refused(gw, gate_key):
    good = _token(gate_key)
    for value in ("", "Bearer", f"Basic {good}", f"Token {good}", "Bearer not.a.jwt!",
                  "Bearer " + "a" * 9000):
        _assert_refused(gw.get("/api/stats", headers={"Authorization": value}))


def test_two_authorization_headers_are_refused(gw, gate_key):
    good = _token(gate_key)
    r = gw.get("/api/stats", headers=[("Authorization", f"Bearer {good}"),
                                      ("Authorization", f"Bearer {good}")])
    _assert_refused(r)


def test_local_tokens_are_not_accepted_in_gateway_mode(gw, tmp_path):
    from sellbird import dashboard_auth as auth
    agent = auth.load_or_create_token(tmp_path / "agent-token")
    user = auth.load_or_create_token(tmp_path / "dashboard-token")
    for token in (agent, user):
        _assert_refused(gw.get("/api/stats", headers={"Authorization": f"Bearer {token}"}))


# ── Gateway mode: host, origin and other untrusted inputs ──


def test_only_the_public_host_is_answered(config, fake_jwks, gate_key, clean_env):
    app = dash.build_gateway_app(config, fetch=fake_jwks)
    auth_header = {"Authorization": f"Bearer {_token(gate_key)}"}
    for base in ("http://127.0.0.1:5555", "https://other.example.test",
                 "https://sellbird.example.test.evil.example"):
        with TestClient(app, base_url=base) as client:
            r = client.get("/api/auth/whoami",
                           headers={**auth_header, "X-Forwarded-Host": PUBLIC_HOST})
            assert r.status_code == 400 and r.json()["error"] == "bad_host"


def test_cross_origin_and_cross_site_requests_are_refused(gw, gate_key):
    auth_header = {"Authorization": f"Bearer {_token(gate_key)}"}
    for extra in ({"Origin": f"http://{PUBLIC_HOST}"},  # not https
                  {"Origin": "https://app.example.test"},  # a sibling host under the cookie domain
                  {"Sec-Fetch-Site": "same-site"},
                  {"Sec-Fetch-Site": "cross-site"}):
        r = gw.get("/api/auth/whoami", headers={**auth_header, **extra})
        assert r.status_code == 403


def test_state_changes_need_the_public_origin(gw, gate_key):
    auth_header = {"Authorization": f"Bearer {_token(gate_key)}"}
    r = gw.post("/api/auth/whoami", headers=auth_header, json={})
    assert r.status_code == 403
    r = gw.post("/api/auth/whoami", headers={**auth_header, "Origin": ORIGIN}, json={})
    # Past the guard: no POST route here, so the router answers (404/405), not the guard.
    assert r.status_code in (404, 405)
    r = gw.post("/api/auth/whoami", headers={**auth_header, "Origin": ORIGIN},
                content=b"a=1")  # a body with no content type
    assert r.status_code == 415
    r = gw.post("/api/auth/whoami",
                headers={**auth_header, "Origin": ORIGIN,
                         "Content-Type": "application/x-www-form-urlencoded"},
                content=b"a=1")
    assert r.status_code == 415


def test_shell_is_public_but_instance_id_is_not(gw):
    assert gw.get("/").status_code == 200
    _assert_refused(gw.get("/api/instance"))


def test_gateway_responses_carry_security_headers(gw, gate_key):
    r = gw.get("/api/auth/whoami", headers={"Authorization": f"Bearer {_token(gate_key)}"})
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["strict-transport-security"].startswith("max-age=")
    assert "access-control-allow-origin" not in r.headers


def test_tokens_are_never_logged(gw, gate_key, caplog):
    caplog.set_level(logging.DEBUG, logger="sellbird")
    good = _token(gate_key)
    bad = _token(gate_key, aud="flint")
    gw.get("/api/auth/whoami", headers={"Authorization": f"Bearer {good}"})
    gw.get("/api/auth/whoami", headers={"Authorization": f"Bearer {bad}"})
    text = caplog.text
    for token in (good, bad):
        assert token not in text
        assert token.split(".")[1] not in text  # nor its claims


# ── The pinned JWKS ──


def _cache(fetch, clock):
    return gwjwks.JwksCache(JWKS_URL, fetch=fetch, clock=clock)


def test_unknown_kid_refresh_is_bounded(gate_key):
    fetch = FakeJwks(_jwks_bytes(_jwk(gate_key)))
    now = [1000.0]
    cache = _cache(fetch, lambda: now[0])

    async def run():
        await cache.get_key(KID)
        assert fetch.calls == 1
        with pytest.raises(gwjwks.JwksError):
            await cache.get_key("made-up")
        assert fetch.calls == 1  # within 60 s of the last fetch: no refresh
        now[0] += 61
        for _ in range(20):  # a burst of made-up key ids
            with pytest.raises(gwjwks.JwksError):
                await cache.get_key("made-up")
        assert fetch.calls == 2  # one refresh, then nothing for 60 s
        now[0] += 30
        with pytest.raises(gwjwks.JwksError):
            await cache.get_key("made-up")
        assert fetch.calls == 2
        now[0] += 31
        with pytest.raises(gwjwks.JwksError):
            await cache.get_key("made-up")
        assert fetch.calls == 3

    asyncio.run(run())


def test_rotated_key_is_picked_up_after_one_refresh(gate_key):
    new_key = _rsa_key()
    fetch = FakeJwks(_jwks_bytes(_jwk(gate_key)))
    now = [1000.0]
    cache = _cache(fetch, lambda: now[0])

    async def run():
        await cache.get_key(KID)
        fetch.body = _jwks_bytes(_jwk(gate_key), _jwk(new_key, "test-key-2"))
        now[0] += 61
        assert (await cache.get_key("test-key-2")) is not None
        assert fetch.calls == 2

    asyncio.run(run())


def test_cache_older_than_five_minutes_is_never_used(gate_key):
    fetch = FakeJwks(_jwks_bytes(_jwk(gate_key)))
    now = [1000.0]
    cache = _cache(fetch, lambda: now[0])

    async def run():
        await cache.get_key(KID)
        fetch.fail = True
        now[0] += 301
        with pytest.raises(gwjwks.JwksError):
            await cache.get_key(KID)  # stale, and the refresh failed: fail closed

    asyncio.run(run())


def test_unreachable_jwks_fails_closed(config, gate_key):
    fetch = FakeJwks(b"")
    fetch.fail = True
    verifier = GateTokenVerifier(config, _cache(fetch, time.monotonic))
    with pytest.raises(GateTokenError):
        asyncio.run(verifier.verify(_token(gate_key)))


def test_oversized_or_malformed_jwks_is_refused(gate_key):
    big = json.dumps({"keys": [_jwk(gate_key)], "pad": "x" * (64 * 1024)}).encode()
    for raw in (big, b"not json", b"[]", b'{"keys": {}}',
                json.dumps({"keys": [_jwk(gate_key, f"k{i}") for i in range(40)]}).encode()):
        with pytest.raises(gwjwks.JwksError):
            gwjwks.parse_jwks(raw)


def test_unusable_jwks_entries_are_skipped(gate_key):
    good = _jwk(gate_key)
    weak = _jwk(_rsa_key(1024), "weak")
    private = {**good, "kid": "private", "d": "AQAB"}
    hmac_key = {"kty": "oct", "kid": "hmac", "k": "c2VjcmV0", "alg": "HS256"}
    wrong_alg = {**good, "kid": "ps", "alg": "PS256"}
    enc = {**good, "kid": "enc", "use": "enc"}
    no_kid = {k: v for k, v in good.items() if k != "kid"}
    keys = gwjwks.parse_jwks(_jwks_bytes(good, weak, private, hmac_key, wrong_alg, enc, no_kid))
    assert set(keys) == {KID}


def test_duplicate_kids_are_dropped(gate_key, attacker_key):
    keys = gwjwks.parse_jwks(_jwks_bytes(_jwk(gate_key), _jwk(attacker_key)))
    assert keys == {}
