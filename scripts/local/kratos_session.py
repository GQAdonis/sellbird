"""Obtain an aal2 Kratos session cookie for one identity, the way a browser would.

Used by scripts/local/make-env.sh for the local stand-in. Standard library only;
run it with ``python3 -I``. It speaks to Kratos's PUBLIC API through flint-gate's
auth-host passthrough (or any base URL given), using Kratos's browser flows with
``Accept: application/json``:

1. login flow, method ``password`` -> an aal1 session cookie;
2. settings flow, method ``totp``: read the TOTP secret Kratos offers and enrol
   it with a code computed here (RFC 6238, SHA-1, 6 digits, 30 s);
3. in a fresh cookie jar (enrolment alone already raises the first session to
   aal2), password login again for an aal1 session, wait for the next TOTP time
   step, then login flow with ``aal=aal2``, method ``totp`` -> that session
   upgraded to aal2;
4. ``GET /sessions/whoami`` must answer 200 with ``aal2``.

Input, from the environment only (nothing secret on the command line):

    KRATOS_PUBLIC_URL    e.g. http://127.0.0.1:4456
    KRATOS_HOST_HEADER   Host to send, e.g. auth.example.test (optional)
    KRATOS_EMAIL         the identity's email trait
    KRATOS_PASSWORD      its password

Output: one line on stdout, the ``Cookie`` header value
``ory_kratos_session=<value>``. Errors go to stderr as a step name and an HTTP
status or Kratos error id; cookies, passwords, secrets and response bodies are
never printed.

Cookies are tracked by hand rather than with a cookie jar: Kratos marks them
``Secure`` and scopes them to the parent domain (``example.test``), and a jar
would refuse to send them back over the stand-in's plain-HTTP loopback port.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request
from http.cookies import SimpleCookie

SESSION_COOKIE = "ory_kratos_session"
TOTP_STEP = 30
TOTP_DIGITS = 6
TIMEOUT = 20


class FlowError(RuntimeError):
    """A Kratos step failed; the message names the step, never a secret."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


class Browser:
    """Just enough of a browser: manual cookies, JSON in and out, no redirects."""

    def __init__(self, base_url: str, host: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.host = host
        self.cookies: dict[str, str] = {}
        self._opener = urllib.request.build_opener(_NoRedirect())

    def request(self, step: str, method: str, path: str,
                body: dict | None = None) -> tuple[int, dict]:
        headers = {"Accept": "application/json"}
        if self.host:
            headers["Host"] = self.host
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=data, method=method,
                                     headers=headers)
        try:
            resp = self._opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as err:
            resp = err
        with resp:
            self._remember(resp.headers.get_all("Set-Cookie") or [])
            raw = resp.read(1_048_576)
            status = resp.status if hasattr(resp, "status") else resp.code
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError:
            payload = {}
        return status, payload if isinstance(payload, dict) else {}

    def _remember(self, set_cookies: list[str]) -> None:
        for header in set_cookies:
            parsed = SimpleCookie()
            try:
                parsed.load(header)
            except Exception:  # an unparsable cookie is not ours to keep
                continue
            for name, morsel in parsed.items():
                expired = morsel["max-age"] in ("0", "-1") or not morsel.value
                if expired:
                    self.cookies.pop(name, None)
                else:
                    self.cookies[name] = morsel.value


def _kratos_error(payload: dict) -> str:
    err = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    ident = err.get("id") or err.get("reason") or ""
    ui = payload.get("ui") if isinstance(payload.get("ui"), dict) else {}
    ids = [str(m.get("id")) for m in ui.get("messages", []) or [] if isinstance(m, dict)]
    for node in ui.get("nodes", []) or []:
        for m in (node.get("messages") or []) if isinstance(node, dict) else []:
            if isinstance(m, dict):
                ids.append(str(m.get("id")))
    return " ".join(filter(None, [str(ident)] + ids)) or "no error id"


def _expect(step: str, status: int, payload: dict, ok: tuple[int, ...] = (200,)) -> dict:
    if status not in ok:
        raise FlowError(f"{step}: HTTP {status} ({_kratos_error(payload)})")
    return payload


def _flow_id_and_csrf(step: str, flow: dict) -> tuple[str, str]:
    flow_id = flow.get("id")
    csrf = ""
    for node in (flow.get("ui") or {}).get("nodes", []):
        attrs = node.get("attributes") or {}
        if attrs.get("name") == "csrf_token":
            csrf = str(attrs.get("value") or "")
    if not flow_id or not csrf:
        raise FlowError(f"{step}: flow without id or csrf_token")
    return str(flow_id), csrf


def _totp_secret(flow: dict) -> str:
    for node in (flow.get("ui") or {}).get("nodes", []):
        attrs = node.get("attributes") or {}
        if attrs.get("id") == "totp_secret_key":
            text = attrs.get("text") or {}
            secret = (text.get("context") or {}).get("secret") or text.get("text")
            if secret:
                return str(secret)
    raise FlowError("settings: Kratos offered no TOTP secret (already enrolled, "
                    "or TOTP disabled)")


def totp(secret: str, at: float | None = None) -> str:
    """RFC 6238 TOTP (SHA-1, 6 digits, 30 s), as Kratos validates it."""
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    counter = int((time.time() if at is None else at) // TOTP_STEP)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % 10 ** TOTP_DIGITS).zfill(TOTP_DIGITS)


def _wait_for_next_step() -> None:
    """Sleep into the next TOTP window so the aal2 code differs from enrolment's."""
    time.sleep(TOTP_STEP - (time.time() % TOTP_STEP) + 1)


def password_login(b: Browser, email: str, password: str) -> None:
    flow = _expect("login init", *b.request("login init", "GET",
                                            "/self-service/login/browser"))
    flow_id, csrf = _flow_id_and_csrf("login init", flow)
    _expect("password login", *b.request(
        "password login", "POST", f"/self-service/login?flow={flow_id}",
        {"method": "password", "identifier": email, "password": password,
         "csrf_token": csrf}))
    if SESSION_COOKIE not in b.cookies:
        raise FlowError("password login: no session cookie was set")


def enrol_totp(b: Browser) -> str:
    flow = _expect("settings init", *b.request("settings init", "GET",
                                               "/self-service/settings/browser"))
    flow_id, csrf = _flow_id_and_csrf("settings init", flow)
    secret = _totp_secret(flow)
    result = _expect("totp enrol", *b.request(
        "totp enrol", "POST", f"/self-service/settings?flow={flow_id}",
        {"method": "totp", "totp_code": totp(secret), "csrf_token": csrf}))
    if result.get("state") not in ("success", None):
        raise FlowError(f"totp enrol: flow state {result.get('state')!r}")
    return secret


def totp_login(b: Browser, secret: str) -> None:
    flow = _expect("aal2 init", *b.request("aal2 init", "GET",
                                           "/self-service/login/browser?aal=aal2"))
    flow_id, csrf = _flow_id_and_csrf("aal2 init", flow)
    result = _expect("totp login", *b.request(
        "totp login", "POST", f"/self-service/login?flow={flow_id}",
        {"method": "totp", "totp_code": totp(secret), "csrf_token": csrf}))
    aal = (result.get("session") or {}).get("authenticator_assurance_level")
    if aal != "aal2":
        raise FlowError(f"totp login: session is {aal!r}, not aal2")


def check_whoami(b: Browser) -> None:
    status, payload = b.request("whoami", "GET", "/sessions/whoami")
    _expect("whoami", status, payload)
    if payload.get("authenticator_assurance_level") != "aal2":
        raise FlowError("whoami: session is not aal2")


def main() -> int:
    try:
        base = os.environ["KRATOS_PUBLIC_URL"]
        email = os.environ["KRATOS_EMAIL"]
        password = os.environ["KRATOS_PASSWORD"]
    except KeyError as missing:
        print(f"kratos_session: {missing.args[0]} is not set", file=sys.stderr)
        return 2
    host = os.environ.get("KRATOS_HOST_HEADER") or None
    try:
        # Enrolling TOTP in a settings flow raises that session to aal2 on its
        # own, so a second-factor login on it is refused with
        # session_already_available. Enrol in one browser, then sign in from a
        # fresh one (no cookies) with password and code, as the operator would.
        enroller = Browser(base, host)
        password_login(enroller, email, password)
        secret = enrol_totp(enroller)
        b = Browser(base, host)
        password_login(b, email, password)
        _wait_for_next_step()
        totp_login(b, secret)
        check_whoami(b)
    except (FlowError, urllib.error.URLError, OSError) as err:
        print(f"kratos_session: {err}", file=sys.stderr)
        return 1
    print(f"{SESSION_COOKIE}={b.cookies[SESSION_COOKIE]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
