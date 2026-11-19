"""Verify the token flint-gate mints for each forwarded request.

The checks follow docs/platform-interface.md ("Minted claims") and RFC 8725:

- compact JWS only, at most ``MAX_TOKEN_LENGTH`` characters;
- header: ``alg`` must be ``RS256`` (our allowlist decides, never the
  header); a non-empty ``kid`` is required; ``jku``, ``x5u``, ``jwk``,
  ``x5c`` and ``crit`` are refused outright, so a token can never point the
  verifier at a key of its choosing;
- the key comes from the pinned JWKS by ``kid`` (``sellbird.auth.jwks``);
- signature, then ``iss`` (exact string), ``aud`` (exactly one string,
  ``sellbird``), ``exp`` (future, 30 s leeway), ``iat`` (not in the future
  beyond 30 s), ``nbf`` when present, and a lifetime (``exp - iat``) of at
  most ``MAX_LIFETIME`` seconds;
- ``sub`` must be a UUID in the allowlist;
- ``aal``, when present, must be ``aal2``.

Any failure, including an unexpected exception, refuses the request. The
token and its claims are never logged; only ``sub`` may be.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Callable

import jwt

from sellbird.auth.config import GatewayConfig
from sellbird.auth.jwks import ALGORITHM, MAX_KID_LENGTH, JwksCache

logger = logging.getLogger("sellbird.auth")

MAX_TOKEN_LENGTH = 8192
LEEWAY_SECONDS = 30
MAX_LIFETIME = 300
REQUIRED_CLAIMS = ("iss", "aud", "sub", "exp", "iat")
FORBIDDEN_HEADERS = ("jku", "x5u", "jwk", "x5c", "crit")
_COMPACT_JWS = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


class GateTokenError(Exception):
    """The token is not acceptable; the request is refused with 401."""


@dataclass(frozen=True)
class VerifiedIdentity:
    sub: str  # canonical lowercase UUID of the allowlisted Kratos identity


def _int_claim(claims: dict, name: str) -> int:
    value = claims.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise GateTokenError(f"'{name}' is not an integer timestamp")
    return value


class GateTokenVerifier:
    def __init__(self, config: GatewayConfig, jwks: JwksCache, *,
                 clock: Callable[[], float] = time.time):
        self.config = config
        self.jwks = jwks
        self._clock = clock

    async def verify(self, token: str) -> VerifiedIdentity:
        """The verified identity, or GateTokenError. Never raises anything else."""
        try:
            return await self._verify(token)
        except GateTokenError:
            raise
        except Exception as e:  # noqa: BLE001 - fail closed on anything unexpected
            raise GateTokenError(f"token rejected ({type(e).__name__})") from e

    async def _verify(self, token: str) -> VerifiedIdentity:
        if not token or len(token) > MAX_TOKEN_LENGTH or not _COMPACT_JWS.fullmatch(token):
            raise GateTokenError("not a compact JWS")

        header = jwt.get_unverified_header(token)
        if not isinstance(header, dict):
            raise GateTokenError("malformed header")
        if header.get("alg") != ALGORITHM:
            raise GateTokenError("algorithm not allowed")
        if any(name in header for name in FORBIDDEN_HEADERS):
            raise GateTokenError("token names its own key or critical extensions")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid or len(kid) > MAX_KID_LENGTH:
            raise GateTokenError("missing kid")

        key = await self.jwks.get_key(kid)

        now = self._clock()
        claims = jwt.decode(
            token,
            key=key.key,
            algorithms=[ALGORITHM],
            audience=self.config.audience,
            issuer=self.config.issuer,
            leeway=LEEWAY_SECONDS,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
                "strict_aud": True,
                "require": list(REQUIRED_CLAIMS),
            },
        )
        if not isinstance(claims, dict):
            raise GateTokenError("malformed claims")
        return self._check_claims(claims, now)

    def _check_claims(self, claims: dict, now: float) -> VerifiedIdentity:
        # Belt and braces over the library's own checks: exact types and values.
        if claims.get("iss") != self.config.issuer or not isinstance(claims.get("iss"), str):
            raise GateTokenError("wrong issuer")
        if claims.get("aud") != self.config.audience or not isinstance(claims.get("aud"), str):
            raise GateTokenError("wrong audience")
        exp = _int_claim(claims, "exp")
        iat = _int_claim(claims, "iat")
        if exp <= now - LEEWAY_SECONDS:
            raise GateTokenError("expired")
        if iat > now + LEEWAY_SECONDS:
            raise GateTokenError("issued in the future")
        if exp - iat > MAX_LIFETIME or exp <= iat:
            raise GateTokenError("lifetime outside the gate's 300 s limit")
        if "nbf" in claims:
            if _int_claim(claims, "nbf") > now + LEEWAY_SECONDS:
                raise GateTokenError("not yet valid")
        if "aal" in claims and claims.get("aal") != "aal2":
            raise GateTokenError("session is not aal2")

        sub = claims.get("sub")
        if not isinstance(sub, str):
            raise GateTokenError("missing sub")
        try:
            canonical = str(uuid.UUID(sub))
        except ValueError as e:
            raise GateTokenError("sub is not a Kratos identity id") from e
        if sub != canonical:  # Kratos ids are canonical lowercase; no other spelling
            raise GateTokenError("sub is not in canonical UUID form")
        if canonical not in self.config.allowed_subs:
            logger.info("Gateway token for a non-allowlisted identity was refused (sub=%s).",
                        canonical)
            raise GateTokenError("identity not allowlisted")
        return VerifiedIdentity(sub=canonical)
