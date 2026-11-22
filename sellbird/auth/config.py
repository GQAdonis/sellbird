"""Which dashboard mode this process runs in, and the gateway settings.

The mode comes from the environment variable ``SELLBIRD_DASHBOARD_MODE``,
read when the dashboard starts. Nothing a request carries can change it.

- unset or empty: ``local`` (the default; loopback bind, token link)
- ``local``: the same, spelled out
- ``gateway``: hosted behind flint-gate (docs/platform-interface.md)
- anything else: refused, so a typo never silently picks a mode

Gateway mode needs every key below (ConfigMap ``sellbird-gateway``). Each is
validated here, so a bad value stops startup instead of weakening a check
later. None of them is a secret.

| Variable | Meaning |
|---|---|
| ``SELLBIRD_PUBLIC_HOST`` | the one accepted ``Host`` (``host`` or ``host:port``); Origin is ``https://`` plus it |
| ``SELLBIRD_GATE_ISSUER`` | expected ``iss``, compared as an exact string |
| ``SELLBIRD_GATE_AUDIENCE`` | expected ``aud`` (``sellbird``) |
| ``SELLBIRD_GATE_JWKS_URL`` | the pinned JWKS location: https, or http only for a loopback or in-cluster host; no credentials |
| ``SELLBIRD_GATE_ALLOWED_SUBS`` | comma-separated Kratos identity ids (UUIDs) |

The algorithm (RS256) is fixed in code, not configurable.
"""

from __future__ import annotations

import ipaddress
import os
import re
import uuid
from dataclasses import dataclass
from typing import Literal, Mapping
from urllib.parse import urlsplit

from sellbird.dashboard_auth import parse_host

Mode = Literal["local", "gateway"]

MODE_ENV = "SELLBIRD_DASHBOARD_MODE"
PUBLIC_HOST_ENV = "SELLBIRD_PUBLIC_HOST"
ISSUER_ENV = "SELLBIRD_GATE_ISSUER"
AUDIENCE_ENV = "SELLBIRD_GATE_AUDIENCE"
JWKS_URL_ENV = "SELLBIRD_GATE_JWKS_URL"
ALLOWED_SUBS_ENV = "SELLBIRD_GATE_ALLOWED_SUBS"

# Set by the container image (Dockerfile ``ENV SELLBIRD_CONTAINER=1``).
CONTAINER_ENV = "SELLBIRD_CONTAINER"

_MAX_SETTING_LENGTH = 2048
_MAX_ALLOWED_SUBS = 16
_TRUE = {"1", "true", "yes", "on"}


class GatewayConfigError(Exception):
    """The gateway settings are missing or invalid; the dashboard won't start."""


@dataclass(frozen=True)
class GatewayConfig:
    public_host: str            # lowercased Host header value, e.g. "sellbird.example.test"
    issuer: str
    audience: str
    jwks_url: str
    allowed_subs: frozenset[str]  # canonical lowercase UUID strings

    @property
    def public_origin(self) -> str:
        return f"https://{self.public_host}"


def dashboard_mode(env: Mapping[str, str] | None = None) -> Mode:
    """The configured mode. Raises GatewayConfigError on an unknown value."""
    env = os.environ if env is None else env
    raw = (env.get(MODE_ENV) or "").strip()
    if raw in ("", "local"):
        return "local"
    if raw == "gateway":
        return "gateway"
    raise GatewayConfigError(
        f"{MODE_ENV} must be 'local' or 'gateway' (or unset for local); "
        "refusing to guess from another value.")


def running_in_container(env: Mapping[str, str] | None = None) -> bool:
    """True inside the Sellbird image or a Kubernetes pod.

    Explicit signals only (the image's ``SELLBIRD_CONTAINER``, the
    ``KUBERNETES_SERVICE_HOST`` every pod gets, and the ``container``
    variable podman and systemd-nspawn set), so a developer machine is never
    mistaken for a container."""
    env = os.environ if env is None else env
    if (env.get(CONTAINER_ENV) or "").strip().lower() in _TRUE:
        return True
    if env.get("KUBERNETES_SERVICE_HOST"):
        return True
    return bool((env.get("container") or "").strip())


def _required(env: Mapping[str, str], name: str) -> str:
    value = (env.get(name) or "").strip()
    if not value:
        raise GatewayConfigError(f"Gateway mode needs {name}.")
    if len(value) > _MAX_SETTING_LENGTH or any(ord(c) <= 32 or ord(c) >= 127 for c in value):
        raise GatewayConfigError(f"{name} must be printable ASCII with no spaces.")
    return value


def _public_host(env: Mapping[str, str]) -> str:
    value = _required(env, PUBLIC_HOST_ENV).lower()
    if "/" in value or "@" in value or parse_host(value) is None:
        raise GatewayConfigError(
            f"{PUBLIC_HOST_ENV} must be a bare host name (optionally host:port), "
            "with no scheme or path, e.g. sellbird.example.test.")
    return value


# One DNS label as Kubernetes and RFC 1123 spell it (lowercase; the host is
# lowercased before matching). Anything else (``_``, ``%``, an empty label)
# never earns the plain-http allowance.
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\Z")
_LOOPBACK_V4 = ipaddress.IPv4Network("127.0.0.0/8")
_LOOPBACK_V6 = ipaddress.IPv6Address("::1")
_IN_CLUSTER_SUFFIXES = (("svc",), ("svc", "cluster", "local"))


def _plain_http_allowed(host: str) -> bool:
    """True when ``host`` may be reached over plain http.

    Only a loopback host (``localhost``, ``*.localhost``, ``127.0.0.0/8``,
    ``::1``) or an in-cluster service name ending in ``.svc`` or
    ``.svc.cluster.local``. Matching is on whole labels of the lowercased
    host, so ``svc.example.test``, ``foo.svc.example.test`` and
    ``127.0.0.1.example.test`` do not qualify.

    A trailing dot is deliberately NOT stripped, so ``localhost.`` or
    ``gate.ns.svc.`` never qualifies (https is still accepted for them). An
    absolute ``name.ns.svc.`` skips the pod's search domains and is looked up
    under a public top-level domain ``svc``, outside the cluster; refusing
    every dotted form keeps the rule to names that cannot leave the cluster
    or the machine.
    """
    host = host.lower()
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        # Explicit ranges rather than ``is_loopback``, whose answer for
        # IPv4-mapped IPv6 addresses differs between Python versions.
        if isinstance(ip, ipaddress.IPv4Address):
            return ip in _LOOPBACK_V4
        return ip == _LOOPBACK_V6
    labels = host.split(".")
    if not all(_DNS_LABEL.match(label) for label in labels):
        return False  # empty label (incl. a trailing dot) or odd characters
    if labels[-1] == "localhost":
        return True
    return any(
        len(labels) > len(suffix) and tuple(labels[-len(suffix):]) == suffix
        for suffix in _IN_CLUSTER_SUFFIXES)


def _jwks_url(env: Mapping[str, str]) -> str:
    value = _required(env, JWKS_URL_ENV)
    try:
        parts = urlsplit(value)
        port = parts.port  # raises ValueError on a bad port
    except ValueError as e:
        raise GatewayConfigError(f"{JWKS_URL_ENV} is not a valid URL.") from e
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise GatewayConfigError(f"{JWKS_URL_ENV} must be an http(s) URL with a host.")
    if parts.username is not None or parts.password is not None:
        raise GatewayConfigError(f"{JWKS_URL_ENV} must not carry credentials.")
    if parts.fragment:
        raise GatewayConfigError(f"{JWKS_URL_ENV} must not have a #fragment.")
    if parts.scheme == "http" and not _plain_http_allowed(parts.hostname):
        # Never echo the value: the message names the variable and the rule.
        raise GatewayConfigError(
            f"{JWKS_URL_ENV} must use https. Plain http is allowed only for a "
            "loopback host (localhost, a name ending in .localhost, "
            "127.0.0.0/8 or ::1) or an in-cluster service name ending in .svc "
            "or .svc.cluster.local.")
    del port
    return value


def _allowed_subs(env: Mapping[str, str]) -> frozenset[str]:
    raw = _required(env, ALLOWED_SUBS_ENV)
    subs = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            subs.add(str(uuid.UUID(item)))
        except ValueError as e:
            raise GatewayConfigError(
                f"{ALLOWED_SUBS_ENV} must list Kratos identity ids (UUIDs), "
                "comma-separated.") from e
    if not subs:
        raise GatewayConfigError(f"Gateway mode needs at least one id in {ALLOWED_SUBS_ENV}.")
    if len(subs) > _MAX_ALLOWED_SUBS:
        raise GatewayConfigError(f"{ALLOWED_SUBS_ENV} lists more than {_MAX_ALLOWED_SUBS} ids.")
    return frozenset(subs)


def load_gateway_config(env: Mapping[str, str] | None = None) -> GatewayConfig:
    """Every gateway setting, validated. Raises GatewayConfigError."""
    env = os.environ if env is None else env
    return GatewayConfig(
        public_host=_public_host(env),
        issuer=_required(env, ISSUER_ENV),
        audience=_required(env, AUDIENCE_ENV),
        jwks_url=_jwks_url(env),
        allowed_subs=_allowed_subs(env),
    )
