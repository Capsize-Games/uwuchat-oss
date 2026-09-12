"""WebSocket tenant-context + DEK-context helper.

WebSocket connections bypass FastAPI's ``@app.middleware("http")`` stack,
so the JWT→tenant context that the auth extension establishes for HTTP
requests is *never* applied to WS handlers.  Without it, every database
operation performed while a socket is open runs against the default
(anonymous) schema — which is why chat conversations were persisted to
``tenant_anonymous`` regardless of which account was signed in.

This module decodes the access token from the WS query string (browsers
cannot set custom headers on a WS upgrade, so the client passes it as
``?token=``) and activates the matching tenant for the life of the
socket.  It **also** resolves and scopes the per-request Data Encryption
Key (DEK) — see :mod:`airunner_services.utils.crypto.dek_cache` — so
that encrypted columns (``UserEncryptedText``) work on WebSocket-originated
writes just as they do on the HTTP path.

Callers MUST check the return value of :func:`resolve_ws_tenant` and
close the socket immediately when ``account_id is None`` — the
framework no longer allows unauthenticated WebSocket connections to
proceed without a valid JWT.
"""

from __future__ import annotations

import contextlib
from typing import Optional, Tuple

from fastapi import WebSocket

from airunner_services.data.tenant import (
    account_id_scope,
    reset_tenant_key,
    set_tenant_key,
    tenant_key_from_schema,
)
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application.get_logger import get_logger
from airunner_services.utils.crypto.dek_cache import (
    cache_get,
    cache_touch,
    dek_scope,
)

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)


def _decode_ws_token(token: str) -> Optional[dict]:
    """Decode a JWT access token via the auth extension, if available."""
    try:
        from extensions.auth.server.jwt import decode_token
    except Exception:
        # Auth extension not installed — single-tenant / dev mode.
        return None
    try:
        return decode_token(token, expected_type="access")
    except Exception:
        logger.debug("Failed to decode WebSocket token", exc_info=True)
        return None


def _extract_token(websocket: WebSocket) -> Optional[str]:
    """Return the bearer token from the WS query string or header."""
    token = websocket.query_params.get("token")
    if token:
        return token
    auth = websocket.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def resolve_ws_tenant(
    websocket: WebSocket,
) -> Tuple[Optional[str], Optional[int]]:
    """Return ``(raw_tenant_key, account_id)`` for an authenticated socket.

    Both values are ``None`` when the socket is unauthenticated or when
    the account is banned, suspended, or deleted.  This ensures the WS
    path enforces the same account-status checks as the HTTP middleware.
    """
    token = _extract_token(websocket)
    if not token:
        return None, None
    payload = _decode_ws_token(token)
    if not payload:
        return None, None
    tenant_key = tenant_key_from_schema(payload.get("tenant", ""))
    account_id: Optional[int] = None
    try:
        account_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        account_id = None

    # ---- Account status check (ban/suspend/delete) ----
    if account_id is not None:
        try:
            from extensions.auth.server.middleware import (
                _check_account_status,
            )
            _status, _db_ver = _check_account_status(account_id)
            if _status is not None:
                logger.info(
                    "WS connection rejected: account %d status=%s",
                    account_id,
                    _status,
                )
                return None, None
            # Reject access tokens whose ``ver`` claim is older than
            # the account's current ``token_version`` (bumped on logout
            # and password-change), matching the HTTP middleware check.
            _token_ver = int(payload.get("ver", 0))
            if _token_ver < _db_ver:
                logger.info(
                    "WS connection rejected: account %d token "
                    "revoked (ver=%d < db_ver=%d)",
                    account_id,
                    _token_ver,
                    _db_ver,
                )
                return None, None
        except RuntimeError:
            # Fail closed — DB unreachable, reject the connection.
            logger.error(
                "WS connection rejected: DB unreachable during "
                "status check for account %d",
                account_id,
            )
            return None, None
    # ---- end account status check ----

    return tenant_key, account_id


@contextlib.contextmanager
def ws_tenant_scope(websocket: WebSocket):
    """Activate the tenant context for an authenticated WS connection.

    Yields ``(tenant_key, account_id)``.  Restores the previous tenant
    on exit.  When the socket is unauthenticated, no override is applied
    and ``(None, None)`` is yielded.

    DEK resolution is intentionally *not* done here — callers must wrap
    each individual RPC / message dispatch with :func:`ws_dek_scope` so
    that the DEK is re-resolved from the cache on every invocation
    (mirroring the HTTP middleware's per-request pattern).  A one-time
    DEK lookup at connection open would survive neither a cache expiry
    nor a server restart, silently breaking decryption for the life of
    the socket.
    """
    tenant_key, account_id = resolve_ws_tenant(websocket)
    token = set_tenant_key(tenant_key) if tenant_key else None
    with account_id_scope(account_id):
        try:
            yield tenant_key, account_id
        finally:
            if token is not None:
                reset_tenant_key(token)


@contextlib.contextmanager
def ws_dek_scope(account_id: int | None):
    """Re-resolve the per-account DEK from the process cache.

    Must be called for every individual RPC dispatch or WS message
    handler invocation — never once per socket lifetime.  Mirrors the
    HTTP auth middleware's per-request behaviour::

        cache_get → set_user_dek → cache_touch → (work) → reset_user_dek

    When *account_id* is ``None`` (unauthenticated socket) this is a
    no-op — no DEK is set and no contextvar is leaked.
    """
    if account_id is None:
        yield
        return

    dek = cache_get(account_id)
    if dek is None:
        # No DEK in cache — proceed with None so the caller can detect
        # the miss and signal the client to re-authenticate rather than
        # silently returning undecryptable ciphertext.
        logger.debug("DEK cache miss for account %s in WS", account_id)
        yield
        return

    cache_touch(account_id)
    with dek_scope(dek):
        yield


__all__ = ["resolve_ws_tenant", "ws_dek_scope", "ws_tenant_scope"]
