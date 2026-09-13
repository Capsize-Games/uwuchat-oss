"""Auth extension — JWT authentication middleware.

Extracts and validates the Bearer token from the ``Authorization``
header on every request (except public paths like /health and /auth/*).
On success, sets ``request.state.account_id`` and configures the tenant
context via ``set_tenant_key()``.

On failure, returns 401 with no further processing.
"""

from __future__ import annotations

from airunner_services.data.tenant import (
    reset_tenant_key,
    set_tenant_key,
    tenant_key_from_schema,
)
from airunner_services.utils.crypto.dek_cache import (
    cache_get,
    cache_touch,
    reset_user_dek,
    set_user_dek,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from extensions.auth.server.jwt import decode_token
from extensions.auth.server.limiter import limiter


def _account_validation_handler(
    request: Request, exc: Exception,
) -> JSONResponse:
    """Map AccountValidationError to HTTP 400."""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


def register(app: FastAPI) -> None:
    """Register the JWT authentication middleware on *app*.

    Called automatically by the extension loader when the module
    exists at ``extensions/auth/server/middleware.py``.
    """
    from airunner_services.api.server_middleware import PUBLIC_PATHS

    from extensions.auth.server.routes import AccountValidationError

    app.state.limiter = limiter
    app.add_exception_handler(
        RateLimitExceeded, _rate_limit_exceeded_handler,
    )
    app.add_exception_handler(
        AccountValidationError, _account_validation_handler,
    )
    app.add_middleware(SlowAPIMiddleware)

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        # Public paths — skip auth.  Single source of truth imported from
        # the framework (airunner_services.api.server_middleware.PUBLIC_PATHS)
        # so this set can never drift from the framework middleware's set.
        path = request.url.path
        if path in PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        # Extract Bearer token.
        #
        # The ?token= query-param fallback is only accepted on WebSocket
        # upgrade requests (browsers cannot set custom headers on the
        # upgrade handshake).  Plain HTTP requests must use the
        # Authorization header — accepting tokens in the query string
        # would leak them into proxy/CDN access logs, browser history,
        # and Referer headers.
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
        elif (
            request.scope.get("type") == "websocket"
            and request.query_params.get("token")
        ):
            token = request.query_params["token"]
        else:
            return JSONResponse(
                status_code=401,
                content={"error": "Missing or invalid Authorization header"},
            )
        payload = decode_token(token, expected_type="access")

        if payload is None:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid or expired token"},
            )

        # Set tenant context for the duration of this request.
        #
        # The JWT carries the fully-qualified schema (e.g. ``tenant_ab12_joe``)
        # but ``set_tenant_key`` expects the *raw* key — the DB session layer
        # re-applies the prefix via ``tenant_schema_for_key``.  Passing the
        # schema directly would double-prefix it (``tenant_tenant_ab12_joe``)
        # and point every query at a non-existent schema.
        tenant_schema = payload.get("tenant", "")
        tenant_key = tenant_key_from_schema(tenant_schema)
        if not tenant_key:
            return JSONResponse(
                status_code=401,
                content={"error": "Token missing tenant context"},
            )

        token = set_tenant_key(tenant_key)
        account_id = int(payload["sub"])
        request.state.account_id = account_id

        # Set the per-request DEK contextvar if a DEK is cached for
        # this account.  This allows UserEncryptedText columns to
        # encrypt/decrypt without re-deriving the KEK on every query.
        # Sliding-expiry touch keeps the cache alive for active users.
        dek = cache_get(account_id)
        dek_token = set_user_dek(dek) if dek is not None else None
        if dek is not None:
            cache_touch(account_id)

        # Enforce deleted / suspended status.  A single-row-by-PK query on
        # the accounts table is negligible overhead and means the server
        # reacts instantly when an admin suspends or deletes an account —
        # no token-version bump required.
        #
        # Deleted accounts get 401 (same as an invalid token).
        # Suspended accounts may only hit the handful of auth endpoints
        # needed to read their status, refresh tokens, or sign out.
        try:
            _status, _db_ver = _check_account_status(
                int(payload["sub"]),
            )
        except RuntimeError:
            if dek_token is not None:
                reset_user_dek(dek_token)
            reset_tenant_key(token)
            return JSONResponse(
                status_code=503,
                content={
                    "error": "Service temporarily unavailable — "
                    "please try again shortly."
                },
            )
        if _status == "deleted":
            if dek_token is not None:
                reset_user_dek(dek_token)
            reset_tenant_key(token)
            return JSONResponse(
                status_code=401,
                content={"error": "Account not found"},
            )
        if _status == "banned":
            if dek_token is not None:
                reset_user_dek(dek_token)
            reset_tenant_key(token)
            return JSONResponse(
                status_code=403,
                content={"error": "Account banned"},
            )
        if _status == "suspended" and not _is_suspended_safe_path(
            request.url.path
        ):
            if dek_token is not None:
                reset_user_dek(dek_token)
            reset_tenant_key(token)
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Your account has been suspended. "
                    "Please contact support."
                },
            )

        # Reject access tokens whose ``ver`` claim is older than the
        # account's current ``token_version`` (bumped on logout and
        # password-change).  This closes the window where a stolen
        # access token remains valid until its TTL expires.
        _token_ver = int(payload.get("ver", 0))
        if _token_ver < _db_ver:
            if dek_token is not None:
                reset_user_dek(dek_token)
            reset_tenant_key(token)
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Token has been revoked "
                    "(logout or password change)"
                },
            )

        try:
            return await call_next(request)
        finally:
            # Always clear DEK and tenant context so neither leaks to
            # the next request handled on this worker's thread.
            if dek_token is not None:
                reset_user_dek(dek_token)
            reset_tenant_key(token)


_SUSPENDED_SAFE_PREFIXES = (
    "/api/v1/auth/me",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
    "/api/v1/auth/verify",
)


def _is_suspended_safe_path(path: str) -> bool:
    """Return True for auth endpoints suspended users may access."""
    return any(path.startswith(prefix) for prefix in _SUSPENDED_SAFE_PREFIXES)


def _check_account_status(
    account_id: int,
) -> tuple[str | None, int]:
    """Return ``(status, token_version)`` for an account ID.

    *status* is ``'deleted'``, ``'suspended'``, ``'banned'``, or
    ``None`` (active).  *token_version* is the account's current token
    version (0 when no explicit logout/bump has occurred).

    Raises ``RuntimeError`` when the database is unreachable — the
    caller MUST treat this as a 503 (fail-closed) rather than silently
    allowing a potentially banned or deleted account through.
    """
    from airunner_services.database.session import public_session_scope

    from extensions.auth.server.models import Account

    try:
        with public_session_scope() as session:
            account = (
                session.query(Account)
                .filter(Account.id == account_id)
                .first()
            )
            if account is None or account.deleted:
                return "deleted", 0
            status: str | None = None
            if account.is_banned:
                status = "banned"
            elif account.is_suspended:
                status = "suspended"
            return status, int(account.token_version or 0)
    except Exception as exc:
        raise RuntimeError(
            f"Database unreachable during account-status check "
            f"for account {account_id}"
        ) from exc
