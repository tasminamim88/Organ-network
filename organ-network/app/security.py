"""
Security primitives, standard library only.

  * Passwords hashed with PBKDF2-HMAC-SHA256 (per-user salt, never plaintext).
  * Auth tokens are HS256 JWTs built by hand so the mechanics are inspectable.

A production system would typically use vetted libraries (passlib, pyjwt) and a
managed secret store; rolling these by hand keeps dependencies minimal and
demonstrates understanding of how the pieces fit together.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 240_000


def hash_password(password: str, *, iterations: int = _ITERATIONS) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{_ALGO}${iterations}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != _ALGO:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), _b64d(salt_b64), int(iters))
        return hmac.compare_digest(dk, _b64d(hash_b64))
    except Exception:
        return False


class TokenError(Exception):
    """Missing, malformed, tampered, or expired token."""


def create_access_token(subject: str, secret: str, *, expires_minutes: int,
                        role: Optional[str] = None, now: Optional[int] = None) -> str:
    now = int(time.time()) if now is None else now
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": str(subject), "role": role, "iat": now,
               "exp": now + expires_minutes * 60}
    signing_input = _b64j(header) + "." + _b64j(payload)
    return f"{signing_input}.{_sign(signing_input, secret)}"


def decode_access_token(token: str, secret: str, *, now: Optional[int] = None) -> dict:
    now = int(time.time()) if now is None else now
    try:
        header_b64, payload_b64, signature = token.split(".")
    except ValueError:
        raise TokenError("Malformed token")
    if not hmac.compare_digest(_sign(f"{header_b64}.{payload_b64}", secret), signature):
        raise TokenError("Bad signature")
    try:
        payload = json.loads(_b64d(payload_b64))
    except Exception:
        raise TokenError("Bad payload")
    if int(payload.get("exp", 0)) < now:
        raise TokenError("Token expired")
    return payload


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _b64j(obj: dict) -> str:
    return _b64(json.dumps(obj, separators=(",", ":"), sort_keys=True).encode())


def _sign(signing_input: str, secret: str) -> str:
    return _b64(hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest())
