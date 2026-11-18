"""The pinned flint-gate signing keys (docs/platform-interface.md, "Issuer and JWKS").

Keys come only from the one configured URL, never from anything a token
names (``jku``, ``x5u``, ``jwk``, ``x5c`` are refused by the verifier before
this cache is consulted). The cache:

- keeps a fetched key set for at most ``MAX_CACHE_AGE`` (5 minutes) and never
  uses an older one, so a key the platform withdraws stops working within
  that window, even if the JWKS can't be fetched again;
- refreshes on an unknown ``kid`` at most once every ``UNKNOWN_KID_INTERVAL``
  (60 seconds), so a stream of made-up key ids can't make it hammer the gate;
- retries an empty or expired cache at most once every ``RETRY_INTERVAL``;
- refuses a response over ``MAX_JWKS_BYTES`` (64 KiB), a redirect, a non-200
  status, more than ``MAX_KEYS`` keys, and any key that is not an RSA
  signing key for RS256 of at least 2048 bits with a non-empty ``kid``;
- fails closed: no usable key means the request is refused.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable

import httpx
from jwt import PyJWK

logger = logging.getLogger("sellbird.auth")

ALGORITHM = "RS256"
MAX_JWKS_BYTES = 64 * 1024
MAX_KEYS = 32
MAX_KID_LENGTH = 256
MIN_RSA_BITS = 2048
MAX_CACHE_AGE = 300.0
UNKNOWN_KID_INTERVAL = 60.0
RETRY_INTERVAL = 5.0
FETCH_TIMEOUT = 5.0

Fetcher = Callable[[str], Awaitable[bytes]]


class JwksError(Exception):
    """No usable signing key; the request is refused."""


async def fetch_jwks(url: str) -> bytes:
    """GET the JWKS: no redirects, no proxy settings from the environment,
    a short timeout, and at most MAX_JWKS_BYTES read."""
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=False,
                                 trust_env=False) as client:
        # identity + raw bytes: a compressed body is never inflated (no
        # decompression bomb); it fails to parse and the fetch fails closed.
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        async with client.stream("GET", url, headers=headers) as resp:
            if resp.status_code != 200:
                raise JwksError(f"JWKS answered HTTP {resp.status_code}")
            declared = resp.headers.get("content-length")
            if declared is not None and declared.strip().isdigit() \
                    and int(declared) > MAX_JWKS_BYTES:
                raise JwksError("JWKS response is larger than 64 KiB")
            body = bytearray()
            async for chunk in resp.aiter_raw():
                body.extend(chunk)
                if len(body) > MAX_JWKS_BYTES:
                    raise JwksError("JWKS response is larger than 64 KiB")
            return bytes(body)


def parse_jwks(raw: bytes) -> dict[str, PyJWK]:
    """The usable RS256 signing keys by kid. Unusable entries are skipped;
    a malformed document raises JwksError."""
    if len(raw) > MAX_JWKS_BYTES:
        raise JwksError("JWKS response is larger than 64 KiB")
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise JwksError("JWKS is not valid JSON") from e
    if not isinstance(doc, dict) or not isinstance(doc.get("keys"), list):
        raise JwksError("JWKS has no 'keys' list")
    entries = doc["keys"]
    if len(entries) > MAX_KEYS:
        raise JwksError(f"JWKS lists more than {MAX_KEYS} keys")
    keys: dict[str, PyJWK] = {}
    duplicates: set[str] = set()
    for entry in entries:
        key = _usable_key(entry)
        if key is None:
            continue
        kid, jwk = key
        if kid in keys:
            duplicates.add(kid)
        keys[kid] = jwk
    for kid in duplicates:  # ambiguous: which key is meant? use neither
        keys.pop(kid, None)
    return keys


def _usable_key(entry: object) -> tuple[str, PyJWK] | None:
    if not isinstance(entry, dict):
        return None
    kid = entry.get("kid")
    if not isinstance(kid, str) or not kid or len(kid) > MAX_KID_LENGTH:
        return None
    if entry.get("kty") != "RSA":
        return None
    if entry.get("alg", ALGORITHM) != ALGORITHM:
        return None
    if entry.get("use", "sig") != "sig":
        return None
    ops = entry.get("key_ops")
    if ops is not None and (not isinstance(ops, list) or "verify" not in ops):
        return None
    if "d" in entry:  # a private key published by mistake: refuse to use it
        return None
    try:
        jwk = PyJWK(entry, algorithm=ALGORITHM)
    except Exception:  # noqa: BLE001 - any parse failure means "not usable"
        return None
    if getattr(jwk.key, "key_size", 0) < MIN_RSA_BITS:
        return None
    return kid, jwk


class JwksCache:
    """Signing keys from one pinned URL, cached and refreshed as described above."""

    def __init__(self, url: str, *, fetch: Fetcher | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.url = url
        self._fetch = fetch or fetch_jwks
        self._clock = clock
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at: float | None = None   # last successful fetch
        self._attempted_at: float | None = None  # last attempt, successful or not
        self._lock = asyncio.Lock()

    def _fresh(self, now: float) -> bool:
        return self._fetched_at is not None and now - self._fetched_at < MAX_CACHE_AGE

    def _may_refresh(self, now: float, interval: float) -> bool:
        return self._attempted_at is None or now - self._attempted_at >= interval

    async def get_key(self, kid: str) -> PyJWK:
        """The key for ``kid``, or JwksError."""
        now = self._clock()
        if self._fresh(now) and kid in self._keys:
            return self._keys[kid]
        async with self._lock:
            now = self._clock()
            fresh = self._fresh(now)
            if fresh and kid in self._keys:
                return self._keys[kid]  # another request refreshed meanwhile
            interval = UNKNOWN_KID_INTERVAL if fresh else RETRY_INTERVAL
            if self._may_refresh(now, interval):
                await self._refresh(now)
            if self._fresh(self._clock()) and kid in self._keys:
                return self._keys[kid]
        raise JwksError("no current signing key matches the token's kid")

    async def _refresh(self, now: float) -> None:
        self._attempted_at = now
        try:
            keys = parse_jwks(await self._fetch(self.url))
        except Exception as e:  # noqa: BLE001 - fail closed on any fetch problem
            logger.warning("Could not refresh the gateway JWKS from the configured URL: %s",
                           type(e).__name__ if not isinstance(e, JwksError) else e)
            return
        self._keys = keys
        self._fetched_at = self._clock()
        if not keys:
            logger.warning("The gateway JWKS has no usable RS256 signing key.")
