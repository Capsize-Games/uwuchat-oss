"""JWT token utilities using PyJWT.

Requires ``pyjwt`` to be installed in the server environment:

    pip install pyjwt
"""

from __future__ import annotations

import datetime
import os

import jwt

_DEV_FALLBACK_SECRET = "dev-jwt-secret-do-not-use-in-production"

_raw_secret = os.environ.get("AIRUNNER_JWT_SECRET", "").strip()
if not _raw_secret or _raw_secret == _DEV_FALLBACK_SECRET:
    if os.environ.get("AIRUNNER_ALLOW_DEV_JWT_SECRET", "") != "1":
        raise RuntimeError(
            "AIRUNNER_JWT_SECRET is unset or equals the hardcoded dev "
            "fallback.  Set AIRUNNER_JWT_SECRET to a strong random "
            "secret, or set AIRUNNER_ALLOW_DEV_JWT_SECRET=1 to "
            "explicitly opt into the dev fallback (local development "
            "only — never in production).  Generate a secret with: "
            "python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    _raw_secret = _DEV_FALLBACK_SECRET

_JWT_SECRET = _raw_secret
_JWT_ALGORITHM = "HS256"
_ACCESS_TOKEN_TTL = int(
    os.environ.get("AIRUNNER_JWT_ACCESS_TTL", "900")  # 15 min
)
_REFRESH_TOKEN_TTL = int(
    os.environ.get("AIRUNNER_JWT_REFRESH_TTL", "604800")  # 7 days
)
_VERIFICATION_TOKEN_TTL = int(
    os.environ.get("AIRUNNER_VERIFICATION_TOKEN_TTL", "86400")  # 24 hours
)


def create_access_token(
    account_id: int,
    tenant_schema: str,
    token_version: int = 0,
) -> str:
    """Return a short-lived JWT access token."""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(account_id),
        "tenant": tenant_schema,
        "ver": int(token_version),
        "iat": now,
        "exp": now + datetime.timedelta(seconds=_ACCESS_TOKEN_TTL),
        "type": "access",
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def create_refresh_token(account_id: int, token_version: int = 0) -> str:
    """Return a longer-lived JWT refresh token."""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(account_id),
        "ver": int(token_version),
        "iat": now,
        "exp": now + datetime.timedelta(seconds=_REFRESH_TOKEN_TTL),
        "type": "refresh",
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


_OAUTH_STATE_TTL = int(
    os.environ.get("AIRUNNER_OAUTH_STATE_TTL", "600")  # 10 min
)
_OAUTH_HANDOFF_TTL = int(
    os.environ.get("AIRUNNER_OAUTH_HANDOFF_TTL", "60")  # 60 s
)


def create_oauth_state_token(extra: dict | None = None) -> str:
    """Return a signed, short-lived CSRF state token for OAuth.

    Stateless by design: nothing is stored server-side, so the flow works
    across multiple worker processes and the state self-expires.

    optional extra claims when the state is valid and unexpired.
    merged into the payload so they round-trip through the OAuth provider
    and are available again in the callback.
    """
    import secrets as _secrets

    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "jti": _secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + datetime.timedelta(seconds=_OAUTH_STATE_TTL),
        "type": "oauth_state",
        **(extra or {}),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def create_oauth_handoff_token(account_id: int) -> str:
    """Return a very short-lived one-time code for the OAuth redirect.

    The browser receives this (not the real tokens) in the callback URL
    and immediately exchanges it via POST for access/refresh tokens, so
    long-lived credentials never land in URLs, logs, or history.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(account_id),
        "iat": now,
        "exp": now + datetime.timedelta(seconds=_OAUTH_HANDOFF_TTL),
        "type": "oauth_handoff",
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def create_verification_token(account_id: int) -> str:
    """Return a short-lived JWT for email verification.

    The token has type "verify" and expires after
    ``AIRUNNER_VERIFICATION_TOKEN_TTL`` seconds (default 24 hours).
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(account_id),
        "iat": now,
        "exp": now + datetime.timedelta(seconds=_VERIFICATION_TOKEN_TTL),
        "type": "verify",
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def decode_token(
    token: str,
    expected_type: str | None = None,
) -> dict | None:
    """Decode and validate a JWT.

    Returns the payload dict on success, or ``None`` when the token is
    invalid, expired, or its ``type`` claim does not match
    *expected_type* (when provided).
    """
    try:
        payload: dict = jwt.decode(
            token,
            _JWT_SECRET,
            algorithms=[_JWT_ALGORITHM],
        )
    except jwt.PyJWTError:
        return None
    if expected_type is not None and payload.get("type") != expected_type:
        return None
    return payload


__all__ = [
    "create_access_token",
    "create_refresh_token",
    "create_verification_token",
    "create_oauth_state_token",
    "create_oauth_handoff_token",
    "decode_token",
]
