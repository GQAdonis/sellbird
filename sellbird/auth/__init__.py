"""Hosted (gateway) sign-in for the dashboard.

A local install never touches this package: the dashboard keeps its loopback
bind and token link (``sellbird.dashboard_auth``). Gateway mode is for a
hosted deployment behind flint-gate, which signs the operator in with Ory
Kratos and forwards each request with a short-lived RS256 token. Sellbird
verifies that token against a pinned JWKS and admits only allowlisted Kratos
identities. The contract is docs/platform-interface.md.

Modules:

- ``config``: the mode switch and the gateway settings, read once from the
  environment at startup (never from a request).
- ``jwks``: the pinned, size-capped, rate-limited key cache.
- ``gate_token``: the token verifier.
- ``gateway_guard``: the ASGI middleware that replaces the local token guard
  in gateway mode, plus the ``/api/auth/whoami`` route.
"""
