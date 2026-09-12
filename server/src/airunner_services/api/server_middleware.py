"""Core API-key and tenant middleware."""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from airunner_services.data.tenant import reset_tenant_key, set_tenant_key

_api_key_cfg: dict = {}


def _load_api_key_config() -> dict:
    api_key = (os.environ.get("AIRUNNER_API_KEY") or "").strip()
    insecure_no_auth = os.environ.get("AIRUNNER_INSECURE_NO_AUTH", "0") == "1"
    allowed_env = (
        os.environ.get("AIRUNNER_ALLOWED_TENANT_KEYS") or ""
    ).strip()
    allowed_tenants = {t.strip() for t in allowed_env.split(",") if t.strip()}
    return {
        "api_key": api_key,
        "require_api_key": bool(api_key),
        "insecure_no_auth": insecure_no_auth,
        "allowed_tenants": allowed_tenants,
    }


def update_api_key_config() -> None:
    global _api_key_cfg
    _api_key_cfg = _load_api_key_config()


def _request_tenant_key(request: Request) -> str | None:
    for header in (
        "x-tenant-key",
        "x-uwuchat-namespace",
        "x-namespace",
    ):
        value = (request.headers.get(header) or "").strip()
        if value:
            return value
    return None


def _resolve_request_api_key(request: Request) -> str:
    provided = (request.headers.get("x-api-key") or "").strip()
    if not provided:
        auth = (request.headers.get("authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            provided = auth.split(" ", 1)[-1].strip()
    return provided


def _check_noauth_access(request: Request) -> bool:
    from .server import is_loopback_request

    path = request.url.path
    if path.startswith("/admin/") and not is_loopback_request(request):
        return False
    from .server import logger as _logger

    if not _api_key_cfg["insecure_no_auth"] and not is_loopback_request(
        request,
    ):
        _logger.warning(
            "Rejecting non-loopback request without API key",
        )
        return False
    return True


async def _tenant_middleware_impl(request: Request, call_next):
    """Scope DB operations to the request's tenant/namespace."""
    from .server import is_loopback_request

    header_value = _request_tenant_key(request)
    tenant_key: str | None = None
    if header_value:
        if _api_key_cfg["require_api_key"]:
            allowed = _api_key_cfg["allowed_tenants"]
            if allowed and header_value in allowed:
                tenant_key = header_value
        elif is_loopback_request(request):
            tenant_key = header_value
    token = set_tenant_key(tenant_key)
    try:
        return await call_next(request)
    finally:
        reset_tenant_key(token)


# Paths that are always public (health + auth endpoints managed by the
# auth extension).  Single source of truth: the auth extension imports
# this same set (extensions/auth/server/middleware.py) so the two
# middleware layers can never drift apart.
PUBLIC_PATHS: set[str] = {
    "/health",
    "/api/v1/health",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/auth/verify",
    "/api/v1/auth/invite-required",
    "/api/v1/auth/oauth/google/login",
    "/api/v1/auth/oauth/google/callback",
    "/api/v1/auth/oauth/twitch/login",
    "/api/v1/auth/oauth/twitch/callback",
    "/api/v1/auth/oauth/capabilities",
    "/api/v1/auth/oauth/exchange",
    "/api/v1/steam/auth/login",
    "/api/v1/steam/auth/callback",
    "/api/v1/itch/auth/callback",
    "/api/v1/embed/text",  # local embedding endpoint (headlesscode)
}

# Back-compat alias — the underscore-prefixed name predates the shared
# constant; keep it working for any internal/importing references.
_PUBLIC_PATHS = PUBLIC_PATHS


def _project_auth_active() -> bool:
    """Return True when a project deployment with auth extension is active.

    When a project (e.g. uwuchat) is deployed, the auth extension handles
    all authentication via JWT, sessions, OAuth, etc.  The core API-key
    middleware is a framework-level guard for standalone deployments;
    it must not interfere with project-level auth.
    """
    return bool(os.environ.get("AIRUNNER_PROJECT", ""))


async def _auth_middleware_impl(request: Request, call_next):
    # When a project with auth extension handles authentication, skip the
    # core API-key check entirely — the JWT middleware already validated
    # the token (or skipped for public paths).
    if _project_auth_active():
        return await call_next(request)

    path = request.url.path
    if path in _PUBLIC_PATHS:
        return await call_next(request)
    if request.method == "OPTIONS":
        return await call_next(request)
    if not _api_key_cfg["require_api_key"]:
        if _check_noauth_access(request):
            return await call_next(request)
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    provided = _resolve_request_api_key(request)
    if not provided or not secrets.compare_digest(
        provided,
        _api_key_cfg["api_key"],
    ):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    return await call_next(request)


def register_middleware(app: FastAPI) -> None:
    """Register tenant and API key auth middleware."""

    @app.middleware("http")
    async def tenant_middleware(request, call_next):
        return await _tenant_middleware_impl(request, call_next)

    @app.middleware("http")
    async def api_key_auth_middleware(request, call_next):
        return await _auth_middleware_impl(request, call_next)


def register_exception_handler(app: FastAPI) -> None:
    """Register the global unhandled-exception handler."""
    from .server import is_loopback_request, logger

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        debug = os.environ.get("AIRUNNER_DEBUG", "0") == "1"
        if debug and is_loopback_request(request):
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "detail": str(exc),
                },
            )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )


def sanitized_http_exception(
    exc: Exception,
    *,
    status_code: int = 500,
    logger: logging.Logger,
    context: str,
) -> HTTPException:
    """Build an ``HTTPException`` whose ``detail`` is safe to expose.

    Use this instead of
    ``HTTPException(status_code=..., detail=str(exc))`` for any
    except-block wrapping an internal error — Starlette's built-in
    HTTPException handler renders ``detail`` directly to the client and
    bypasses ``global_exception_handler`` above.
    """
    from airunner_services.utils.error_sanitizer import log_and_sanitize

    message = log_and_sanitize(exc, logger=logger, context=context)
    return HTTPException(status_code=status_code, detail=message)
