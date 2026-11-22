"""The gateway JWKS address rule (openspec/changes/hosted-small-fixes, task 1.1).

Rule: ``SELLBIRD_GATE_JWKS_URL`` must be https, except that plain http stays
allowed for a loopback host (``localhost``, ``*.localhost``, ``127.0.0.0/8``,
``::1``) or an in-cluster service name ending in ``.svc`` or
``.svc.cluster.local``. Hosts compare case-insensitively on whole labels, a
trailing dot never earns the http allowance, and everything refused before
(credentials, a fragment, a bad port, no host, another scheme) stays refused.
A refusal names the variable and never echoes the value.

Hosts are example.test placeholders and the in-cluster name the deployed
configuration uses.
"""

from __future__ import annotations

import pytest

from sellbird.auth import config as gwconfig

IN_CLUSTER = "flint-gate.flint-gate.svc.cluster.local"

BASE_ENV = {
    gwconfig.MODE_ENV: "gateway",
    gwconfig.PUBLIC_HOST_ENV: "sellbird.example.test",
    gwconfig.ISSUER_ENV: "https://gate.example.test",
    gwconfig.AUDIENCE_ENV: "sellbird",
    gwconfig.ALLOWED_SUBS_ENV: "0000000a-0000-4000-8000-00000000000b",
}


def _load(jwks_url: str) -> gwconfig.GatewayConfig:
    return gwconfig.load_gateway_config({**BASE_ENV, gwconfig.JWKS_URL_ENV: jwks_url})


@pytest.mark.parametrize("url", [
    # https: any host
    "https://gate.example.test/.well-known/jwks.json",
    "https://gate.example.test:8443/.well-known/jwks.json",
    "https://gate.example.test./.well-known/jwks.json",
    # http: in-cluster service names (the deployed address first)
    f"http://{IN_CLUSTER}:4456/.well-known/jwks.json",
    "http://flint-gate.flint-gate.svc:4456/.well-known/jwks.json",
    "http://FLINT-GATE.Flint-Gate.SVC.Cluster.Local:4456/.well-known/jwks.json",
    # http: loopback
    "http://localhost:4456/.well-known/jwks.json",
    "http://LOCALHOST/.well-known/jwks.json",
    "http://gate.localhost:4456/.well-known/jwks.json",
    "http://127.0.0.1:4456/.well-known/jwks.json",
    "http://127.10.20.30/.well-known/jwks.json",
    "http://[::1]:4456/.well-known/jwks.json",
])
def test_jwks_url_accepted(url):
    assert _load(url).jwks_url == url


@pytest.mark.parametrize("url", [
    # a public or private host over plain http
    "http://gate.example.test/.well-known/jwks.json",
    "http://10.0.0.5/.well-known/jwks.json",
    "http://169.254.169.254/.well-known/jwks.json",
    # look-alikes of the allowed suffixes
    "http://svc.example.test/.well-known/jwks.json",
    "http://foo.svc.example.test/.well-known/jwks.json",
    f"http://{IN_CLUSTER}.example.test/.well-known/jwks.json",
    "http://127.0.0.1.example.test/.well-known/jwks.json",
    "http://localhost.example.test/.well-known/jwks.json",
    "http://foosvc/.well-known/jwks.json",
    "http://gate.ns.notsvc/.well-known/jwks.json",
    # trailing dot: deliberately never allowed over http
    f"http://{IN_CLUSTER}.:4456/.well-known/jwks.json",
    "http://flint-gate.flint-gate.svc./.well-known/jwks.json",
    "http://localhost./.well-known/jwks.json",
    # malformed names that only look like an allowed suffix
    "http://.svc/.well-known/jwks.json",
    "http://flint-gate..svc/.well-known/jwks.json",
    "http://flint_gate.ns.svc/.well-known/jwks.json",
    # only ::1 counts as IPv6 loopback
    "http://[::ffff:127.0.0.1]/.well-known/jwks.json",
])
def test_jwks_url_http_refused(url):
    with pytest.raises(gwconfig.GatewayConfigError, match="must use https"):
        _load(url)


@pytest.mark.parametrize("url", [
    "https://user:pw@gate.example.test/.well-known/jwks.json",
    "http://user@localhost/.well-known/jwks.json",
    f"http://user:pw@{IN_CLUSTER}:4456/.well-known/jwks.json",
    "https://gate.example.test/.well-known/jwks.json#frag",
    f"http://{IN_CLUSTER}:4456/.well-known/jwks.json#frag",
    "https://gate.example.test:99999/.well-known/jwks.json",
    "http://localhost:notaport/.well-known/jwks.json",
    "https:///.well-known/jwks.json",
    "ftp://gate.example.test/.well-known/jwks.json",
    "file:///etc/jwks.json",
])
def test_jwks_url_previous_refusals_still_hold(url):
    with pytest.raises(gwconfig.GatewayConfigError, match=gwconfig.JWKS_URL_ENV):
        _load(url)


@pytest.mark.parametrize("url", [
    "http://gate.example.test/.well-known/jwks.json",
    f"http://{IN_CLUSTER}.:4456/.well-known/jwks.json",
])
def test_jwks_url_refusal_names_the_variable_not_the_value(url):
    with pytest.raises(gwconfig.GatewayConfigError) as caught:
        _load(url)
    message = str(caught.value)
    assert gwconfig.JWKS_URL_ENV in message
    assert "https" in message
    assert url not in message
    assert "gate.example.test" not in message
    assert IN_CLUSTER not in message
