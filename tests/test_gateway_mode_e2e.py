"""Gateway mode end to end, black box (SCN-AUTH-001).

Runs against a live stack: flint-gate (with Kratos behind it) in front of the
packaged Sellbird image in gateway mode. Nothing here imports Sellbird; it
speaks HTTP only. The whole module SKIPS when ``SELLBIRD_GATEWAY_URL`` is
unset. Once it is set, every other variable below is required and a missing
one FAILS the test (a boundary run must not pass by skipping).

Environment interface (documented in
openspec/changes/hosted-gateway-mode/design.md; the local stand-in's setup
script under scripts/local/ provides the values, from an uncommitted .env):

| Variable | Meaning |
|---|---|
| ``SELLBIRD_GATEWAY_URL`` | flint-gate's proxy URL fronting Sellbird, e.g. ``http://localhost:4456`` |
| ``SELLBIRD_E2E_HOST`` | optional ``Host`` header for gateway requests (the site domain flint-gate routes on); default: from the URL |
| ``SELLBIRD_E2E_ALLOWED_SUB`` | the allowlisted Kratos identity id (the expected principal) |
| ``SELLBIRD_E2E_SESSION_COOKIE`` | ``Cookie`` header value of an aal2 Kratos session for that identity |
| ``SELLBIRD_E2E_OTHER_SESSION_COOKIE`` | ``Cookie`` header value of an aal2 session for a second, non-allowlisted identity |
| ``SELLBIRD_E2E_DIRECT_URL`` | Sellbird's own port, bypassing flint-gate, e.g. ``http://localhost:5555`` |
| ``SELLBIRD_E2E_PUBLIC_HOST`` | Sellbird's ``SELLBIRD_PUBLIC_HOST``, sent as ``Host`` on direct requests |
| ``SELLBIRD_E2E_GATE_KEY_FILE`` | path to the stand-in flint-gate's RS256 signing key (PEM), generated per run, never committed |
| ``SELLBIRD_E2E_GATE_KID`` | that key's ``kid`` as published in the JWKS |
| ``SELLBIRD_E2E_GATE_ISSUER`` | flint-gate's issuer string (Sellbird's ``SELLBIRD_GATE_ISSUER``) |

Direct requests carry tokens signed with the gate's real key, so a refusal
there is for the stated reason (wrong audience, expiry, identity), which the
positive control with the same key proves. Session cookies and keys are never
printed; assertion messages name only status codes.
"""

from __future__ import annotations

import os
import time
import uuid
from urllib.parse import urlsplit

import pytest

GATEWAY_URL = os.environ.get("SELLBIRD_GATEWAY_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not GATEWAY_URL,
    reason="SELLBIRD_GATEWAY_URL is not set: no gateway stack to test against "
           "(run the local stand-in, then set it; see design.md of hosted-gateway-mode)")

AUDIENCE = "sellbird"
WHOAMI = "/api/auth/whoami"
DATA_PATH = "/api/stats"


def _need(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.fail(f"{name} must be set when SELLBIRD_GATEWAY_URL is set "
                    "(see the module docstring)", pytrace=False)
    return value


@pytest.fixture(scope="module")
def httpx_mod():
    return pytest.importorskip("httpx")


@pytest.fixture(scope="module")
def jwt_mod():
    return pytest.importorskip("jwt")


@pytest.fixture(scope="module")
def allowed_sub() -> str:
    return str(uuid.UUID(_need("SELLBIRD_E2E_ALLOWED_SUB")))


@pytest.fixture(scope="module")
def gateway(httpx_mod):
    host = os.environ.get("SELLBIRD_E2E_HOST", "").strip() or urlsplit(GATEWAY_URL).netloc
    with httpx_mod.Client(base_url=GATEWAY_URL, headers={"Host": host}, timeout=15.0,
                          follow_redirects=False, trust_env=False) as client:
        yield client


@pytest.fixture(scope="module")
def direct(httpx_mod):
    url = _need("SELLBIRD_E2E_DIRECT_URL")
    host = _need("SELLBIRD_E2E_PUBLIC_HOST")
    with httpx_mod.Client(base_url=url, headers={"Host": host}, timeout=15.0,
                          follow_redirects=False, trust_env=False) as client:
        yield client


@pytest.fixture(scope="module")
def mint(jwt_mod):
    """Sign a token with the stand-in gate's real key (for direct requests)."""
    with open(_need("SELLBIRD_E2E_GATE_KEY_FILE"), "rb") as f:
        key = f.read()
    kid = _need("SELLBIRD_E2E_GATE_KID")
    issuer = _need("SELLBIRD_E2E_GATE_ISSUER")

    def _mint(sub: str, **overrides) -> str:
        now = int(time.time())
        claims = {"iss": issuer, "aud": AUDIENCE, "sub": sub, "iat": now, "exp": now + 120,
                  "jti": str(uuid.uuid4()), "aal": "aal2"}
        claims.update(overrides)
        return jwt_mod.encode(claims, key, algorithm="RS256", headers={"kid": kid})

    return _mint


def _assert_refused_without_data(response, allowed_sub: str):
    assert response.status_code == 401, f"expected 401, got {response.status_code}"
    body = response.text
    assert allowed_sub not in body
    assert "principal" not in body


# ── Through flint-gate: the real sign-in path ──


def test_allowlisted_session_resolves_to_the_allowlisted_identity(gateway, allowed_sub):
    r = gateway.get(WHOAMI, headers={"Cookie": _need("SELLBIRD_E2E_SESSION_COOKIE")})
    assert r.status_code == 200, f"expected 200, got {r.status_code}"
    assert r.json() == {"mode": "gateway", "principal": "user", "sub": allowed_sub}


def test_forged_headers_do_not_change_the_resolved_identity(gateway, allowed_sub):
    other = "00000000-0000-4000-8000-0000000000ff"
    r = gateway.get(WHOAMI, headers={
        "Cookie": _need("SELLBIRD_E2E_SESSION_COOKIE"),
        # (No forged Authorization here: flint-gate may refuse a request with
        # two credentials outright, which is safe but not this test's point.)
        "x-flint-user-id": other,
        "X-Forwarded-User": other,
    })
    assert r.status_code == 200, f"expected 200, got {r.status_code}"
    assert r.json()["sub"] == allowed_sub


def test_forged_identity_header_without_a_session_is_refused(gateway, allowed_sub):
    r = gateway.get(DATA_PATH, headers={"x-flint-user-id": allowed_sub,
                                        "x-flint-auth-method": "kratos_session"})
    _assert_refused_without_data(r, allowed_sub)


def test_no_session_is_refused(gateway, allowed_sub):
    _assert_refused_without_data(gateway.get(DATA_PATH), allowed_sub)


def test_non_allowlisted_identity_is_refused(gateway, allowed_sub):
    r = gateway.get(DATA_PATH, headers={"Cookie": _need("SELLBIRD_E2E_OTHER_SESSION_COOKIE")})
    _assert_refused_without_data(r, allowed_sub)


# ── Straight to Sellbird: the gate is the only way in ──


def test_direct_positive_control(direct, mint, allowed_sub):
    r = direct.get(WHOAMI, headers={"Authorization": f"Bearer {mint(allowed_sub)}"})
    assert r.status_code == 200, f"expected 200, got {r.status_code}"
    assert r.json()["sub"] == allowed_sub


def test_direct_without_a_token_is_refused(direct, allowed_sub):
    _assert_refused_without_data(direct.get(DATA_PATH), allowed_sub)


def test_direct_forged_identity_header_is_refused(direct, allowed_sub):
    r = direct.get(DATA_PATH, headers={"x-flint-user-id": allowed_sub,
                                       "X-Forwarded-User": allowed_sub})
    _assert_refused_without_data(r, allowed_sub)


def test_direct_cookie_alone_is_refused(direct, allowed_sub):
    r = direct.get(DATA_PATH, headers={"Cookie": _need("SELLBIRD_E2E_SESSION_COOKIE")})
    _assert_refused_without_data(r, allowed_sub)


def test_direct_wrong_audience_is_refused(direct, mint, allowed_sub):
    r = direct.get(DATA_PATH, headers={"Authorization": f"Bearer {mint(allowed_sub, aud='flint')}"})
    _assert_refused_without_data(r, allowed_sub)


def test_direct_expired_token_is_refused(direct, mint, allowed_sub):
    now = int(time.time())
    token = mint(allowed_sub, iat=now - 400, exp=now - 100)
    r = direct.get(DATA_PATH, headers={"Authorization": f"Bearer {token}"})
    _assert_refused_without_data(r, allowed_sub)


def test_direct_non_allowlisted_identity_is_refused(direct, mint, allowed_sub):
    token = mint("00000000-0000-4000-8000-0000000000fe")
    r = direct.get(DATA_PATH, headers={"Authorization": f"Bearer {token}"})
    _assert_refused_without_data(r, allowed_sub)
