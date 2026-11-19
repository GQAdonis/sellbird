"""Who may use the dashboard API in gateway mode.

This replaces ``dashboard_auth.DashboardGuard`` when, and only when, the
process started with ``SELLBIRD_DASHBOARD_MODE=gateway`` (see
``sellbird.dashboard.start_dashboard``). The local guard and its token are
not involved at all: the dashboard token is never read, created or printed,
and the agent token is never accepted, so there is no ``agent`` principal.

Every request passes, in order:

1. Host: exactly one ``Host`` header equal to ``SELLBIRD_PUBLIC_HOST``.
   ``X-Forwarded-*``, ``Forwarded`` and every ``x-flint-*`` header are never
   read (uvicorn also runs with ``proxy_headers=False``).
2. Browser provenance: an ``Origin``, when present, must be exactly
   ``https://`` plus the public host, and ``Sec-Fetch-Site`` must be
   ``same-origin`` or ``none`` (the top-level navigation to ``/`` is the one
   exception, as locally). State-changing methods must carry that ``Origin``.
   The Kratos cookie is scoped to the parent domain, so another application
   host under it is "same-site": these checks, not the cookie, stop it from
   making the gate act for the operator here.
3. Public shell: ``GET``/``HEAD`` of ``/`` and ``/static/*`` only (no data).
   ``/api/instance`` is not public here: it exists for the local MCP agent,
   which gateway mode does not serve.
4. Bearer token: exactly one ``Authorization: Bearer <jwt>`` header, verified
   by ``GateTokenVerifier`` (pinned JWKS, RS256, iss, aud, kid, exp, iat,
   allowlisted ``sub``). Cookies are never read. A refusal is ``401`` with an
   empty body. A verified token becomes principal ``user``; its ``sub`` is
   recorded as ``request.state.gate_sub``.
5. Mutations with a body must be ``application/json``.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request

from sellbird.auth.config import GatewayConfig
from sellbird.auth.gate_token import GateTokenError, GateTokenVerifier
from sellbird.dashboard_auth import SECURITY_HEADERS

logger = logging.getLogger("sellbird.auth")

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

GATEWAY_SECURITY_HEADERS = SECURITY_HEADERS + [
    # Served only over https through the shared Gateway.
    (b"strict-transport-security", b"max-age=31536000"),
]
_REPLACED = {h for h, _ in GATEWAY_SECURITY_HEADERS}


def is_gateway_public_path(method: str, path: str) -> bool:
    if method not in ("GET", "HEAD"):
        return False
    if path == "/":
        return True
    if not path.startswith("/static/"):
        return False
    return all(seg not in ("", ".", "..") for seg in path[len("/static/"):].split("/"))


def _bearer(header_values: list[str]) -> str | None:
    if len(header_values) != 1:
        return None
    scheme, _, presented = header_values[0].partition(" ")
    if scheme.lower() != "bearer":
        return None
    presented = presented.strip()
    return presented or None


def _is_json(content_type: str) -> bool:
    return content_type.split(";", 1)[0].strip().lower() == "application/json"


class GatewayGuard:
    """ASGI middleware applying the checks in the module docstring."""

    def __init__(self, app, config: GatewayConfig, verifier: GateTokenVerifier):
        self.app = app
        self.config = config
        self.verifier = verifier

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return

        headers: dict[str, list[str]] = {}
        for k, v in scope.get("headers") or []:
            headers.setdefault(k.decode("latin-1").lower(), []).append(v.decode("latin-1"))

        async def send_secured(message):
            if message["type"] == "http.response.start":
                existing = [(k, v) for k, v in message.get("headers", [])
                            if k.lower() not in _REPLACED]
                message = {**message, "headers": existing + GATEWAY_SECURITY_HEADERS}
            await send(message)

        async def deny(status: int, code: str, message: str):
            body = json.dumps({"error": code, "message": message}).encode()
            await send_secured({"type": "http.response.start", "status": status,
                                "headers": [(b"content-type", b"application/json"),
                                            (b"content-length", str(len(body)).encode())]})
            await send_secured({"type": "http.response.body", "body": body})

        async def unauthorized():
            # No body at all: a refused request learns nothing, and carries no data.
            await send_secured({"type": "http.response.start", "status": 401,
                                "headers": [(b"content-length", b"0"),
                                            (b"www-authenticate", b'Bearer realm="sellbird"')]})
            await send_secured({"type": "http.response.body", "body": b""})

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")

        # 1. Host, before anything else.
        hosts = headers.get("host", [])
        if len(hosts) != 1 or hosts[0].strip().lower() != self.config.public_host:
            return await deny(400, "bad_host", "This dashboard only answers to its public host.")

        # 2. Browser provenance.
        public = is_gateway_public_path(method, path)
        navigation = (method in ("GET", "HEAD") and path == "/"
                      and headers.get("sec-fetch-mode", [""])[0] == "navigate"
                      and headers.get("sec-fetch-dest", [""])[0] == "document")
        origins = headers.get("origin", [])
        origin_ok = len(origins) == 1 and origins[0].lower() == self.config.public_origin
        if origins and not origin_ok and not navigation:
            return await deny(403, "cross_origin", "Cross-origin requests are refused.")
        site = headers.get("sec-fetch-site", [])
        if site and site[0].lower() not in ("same-origin", "none") and not navigation:
            return await deny(403, "cross_origin", "Cross-site requests are refused.")
        if method in _UNSAFE_METHODS and not origin_ok:
            return await deny(403, "cross_origin",
                              "State-changing requests must come from this dashboard's origin.")

        if public:
            return await self.app(scope, receive, send_secured)

        # 3. The gate's token, and nothing else (no cookie, no x-flint-*, no agent token).
        token = _bearer(headers.get("authorization", []))
        if token is None:
            return await unauthorized()
        try:
            identity = await self.verifier.verify(token)
        except GateTokenError as e:
            logger.debug("Gateway request refused: %s", e)
            return await unauthorized()
        state = scope.setdefault("state", {})
        state["principal"] = "user"
        state["gate_sub"] = identity.sub

        # 4. Mutations carry JSON or nothing.
        if method in _UNSAFE_METHODS:
            length = headers.get("content-length", ["0"])[0].strip()
            has_body = bool(headers.get("transfer-encoding")) or length not in ("", "0")
            if has_body and not _is_json(headers.get("content-type", [""])[0]):
                return await deny(415, "unsupported_media_type",
                                  "Request bodies must be application/json.")

        return await self.app(scope, receive, send_secured)


# Who the gateway says this is. Gateway mode only (never mounted locally), and
# behind the guard like every other API route.
whoami_router = APIRouter()


@whoami_router.get("/api/auth/whoami")
async def whoami(request: Request):
    state = request.scope.get("state") or {}
    return {"mode": "gateway", "principal": state.get("principal"), "sub": state.get("gate_sub")}
