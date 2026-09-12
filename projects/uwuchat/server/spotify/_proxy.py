"""FastSearch proxy helpers for Spotify RPC handlers."""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
from typing import Any

import jwt

from airunner_services.api.ws_tenant import resolve_ws_tenant

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────

_FS_BASE = os.environ.get("FASTSEARCH_BASE_URL", "").rstrip("/")
_FS_TIMEOUT = 30  # seconds

# Shared JWT secret — must match FastSearch SPOTIFY_STATE_JWT_SECRET.
_JWT_SECRET = os.environ.get("SPOTIFY_STATE_JWT_SECRET", "").strip()
_JWT_ALGORITHM = "HS256"
_JWT_TTL_SECONDS = int(os.environ.get("SPOTIFY_STATE_TTL", "600"))


def _spotify_auth_jwt(account_id: int) -> str | None:
    """Generate a short-lived JWT for authenticating to FastSearch."""
    if not _JWT_SECRET:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "user_id": account_id,
        "iat": now,
        "exp": now + datetime.timedelta(seconds=_JWT_TTL_SECONDS),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def _fs_headers(account_id: int) -> dict[str, str]:
    """Return headers for a FastSearch Spotify API request."""
    token = _spotify_auth_jwt(account_id)
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _fs_request(
    method: str, path: str, body: dict | None, account_id: int,
) -> dict:
    """Make a synchronous HTTP request to FastSearch.

    Returns ``{"status": int, "body": dict}`` on success or error.
    """
    import requests as _requests

    url = f"{_FS_BASE}{path}"
    headers = _fs_headers(account_id)
    try:
        if method == "GET":
            resp = _requests.get(url, headers=headers, timeout=_FS_TIMEOUT)
        elif method == "POST":
            resp = _requests.post(
                url, json=body, headers=headers, timeout=_FS_TIMEOUT,
            )
        else:
            return {"status": 405, "body": {"error": "Method not allowed"}}
        resp.raise_for_status()
        data = resp.json()
        return {"status": resp.status_code, "body": data}
    except Exception as exc:
        logger.debug(
            "FastSearch proxy error %s %s: %s", method, path, exc,
        )
        return {
            "status": 502,
            "body": {"error": f"FastSearch unavailable: {exc}"},
        }


async def _fastsearch_proxy(
    method: str,
    path: str,
    body: dict | None = None,
    account_id: int | None = None,
) -> dict[str, Any]:
    """Proxy a request to FastSearch in a thread to avoid blocking."""
    return await asyncio.to_thread(
        _fs_request, method, path, body, account_id,
    )


def require_self(
    account_id: int, path_params: dict, param: str,
) -> dict[str, Any] | None:
    """Return an error dict if *account_id* doesn't match the URL param."""
    raw = path_params.get(param, "")
    try:
        target_id = int(raw)
    except (ValueError, TypeError):
        return {"status": 400, "body": {"error": f"Invalid {param}"}}
    if target_id != account_id:
        return {"status": 403, "body": {"error": "Forbidden"}}
    return None


def require_ws_auth(kw: dict[str, Any]) -> tuple[Any, int | None, dict | None]:
    """Resolve auth from an RPC handler's ``**kw``.

    Returns ``(ws, account_id, error)`` — exactly one of *account_id* or
    *error* is not None.
    """
    ws = kw.get("ws")
    if ws is None:
        return None, None, {
            "status": 400, "body": {"error": "WebSocket required"},
        }
    _tenant, account_id = resolve_ws_tenant(ws)
    if account_id is None:
        return ws, None, {
            "status": 401, "body": {"error": "Authentication required"},
        }
    return ws, account_id, None
