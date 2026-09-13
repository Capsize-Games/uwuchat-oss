"""Spotify integration — framework-level RPC handlers.

Proxies Spotify API calls to FastSearch and generates OAuth PKCE state
tokens.  Self-contained — no imports from ``projects.uwuchat``.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import secrets as _secrets
from typing import Any

import jwt
import requests as _requests

from airunner_services.api.routes.events import _rpc_register
from airunner_services.api.ws_tenant import resolve_ws_tenant

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────

_STATE_SECRET = os.environ.get("SPOTIFY_STATE_JWT_SECRET", "").strip()
_STATE_ALGORITHM = "HS256"
_STATE_TTL_SECONDS = int(os.environ.get("SPOTIFY_STATE_TTL", "600"))

_INSTANCE_URL = os.environ.get(
    "AIRUNNER_SITE_URL", "http://localhost:5173",
).strip().rstrip("/")

_FASTSEARCH_BASE_URL = os.environ.get(
    "FASTSEARCH_BASE_URL", "",
).rstrip("/")
_FASTSEARCH_TIMEOUT = 30


# ── FastSearch proxy helpers (inlined from _proxy.py) ──────────────────


def _spotify_auth_jwt(account_id: int) -> str | None:
    """Generate a short-lived JWT for authenticating to FastSearch."""
    if not _STATE_SECRET:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "user_id": account_id,
        "iat": now,
        "exp": now + datetime.timedelta(seconds=_STATE_TTL_SECONDS),
    }
    return jwt.encode(
        payload, _STATE_SECRET, algorithm=_STATE_ALGORITHM,
    )


def _fastsearch_headers(account_id: int) -> dict[str, str]:
    """Return headers for a FastSearch Spotify API request."""
    token = _spotify_auth_jwt(account_id)
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _fastsearch_request(
    method: str, path: str, body: dict | None, account_id: int,
) -> dict[str, Any]:
    """Make a synchronous HTTP request to FastSearch."""
    url = f"{_FASTSEARCH_BASE_URL}{path}"
    headers = _fastsearch_headers(account_id)
    try:
        if method == "GET":
            resp = _requests.get(
                url, headers=headers, timeout=_FASTSEARCH_TIMEOUT,
            )
        elif method == "POST":
            resp = _requests.post(
                url, json=body, headers=headers,
                timeout=_FASTSEARCH_TIMEOUT,
            )
        else:
            return {
                "status": 405, "body": {"error": "Method not allowed"},
            }
        resp.raise_for_status()
        return {"status": resp.status_code, "body": resp.json()}
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
        _fastsearch_request, method, path, body, account_id,
    )


# ── Auth / validation helpers (inlined from _proxy.py) ────────────────


def _require_self(
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


def _require_ws_auth(
    kw: dict[str, Any],
) -> tuple[Any, int | None, dict | None]:
    """Resolve auth from an RPC handler's ``**kw``.

    Returns ``(ws, account_id, error)`` — exactly one of *account_id*
    or *error* is not None.
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


def _resolve_and_auth(
    kw: dict[str, Any],
) -> tuple[int | None, dict | None]:
    """Resolve ws, authenticate, and match path user_id to account.

    Returns ``(account_id, error)`` — exactly one is not None.
    """
    _, account_id, err = _require_ws_auth(kw)
    if err:
        return None, err
    path_params = kw.get("path_params", {})
    err = _require_self(account_id, path_params, "user_id")
    if err:
        return None, err
    return account_id, None


# ── RPC handlers ───────────────────────────────────────────────────────


@_rpc_register("POST", "/api/v1/spotify/generate-state")
async def _rpc_generate_state(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """Generate a signed JWT state token for the Spotify OAuth PKCE flow."""
    ws = kw.get("ws")
    if ws is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}

    _tenant, account_id = resolve_ws_tenant(ws)
    if account_id is None:
        return {
            "status": 401,
            "body": {"error": "Authentication required"},
        }

    if not _STATE_SECRET:
        return {
            "status": 503,
            "body": {
                "error": (
                    "Spotify integration is not configured. "
                    "Set SPOTIFY_STATE_JWT_SECRET to enable."
                ),
            },
        }

    code_verifier = (body or {}).get("code_verifier", "")
    if not code_verifier:
        return {
            "status": 400,
            "body": {"error": "code_verifier is required"},
        }

    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "user_id": account_id,
        "code_verifier": code_verifier,
        "uwuchat_instance": _INSTANCE_URL,
        "nonce": _secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + datetime.timedelta(seconds=_STATE_TTL_SECONDS),
        "type": "spotify_oauth_state",
    }
    state = jwt.encode(
        payload, _STATE_SECRET, algorithm=_STATE_ALGORITHM,
    )
    return {"status": 200, "body": {"state": state}}


@_rpc_register("GET", "/api/v1/spotify/status/{user_id}")
async def _rpc_spotify_status(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """Proxy GET /api/v1/spotify/status/{user_id} to FastSearch."""
    account_id, err = _resolve_and_auth(kw)
    if err:
        return err
    return await _fastsearch_proxy(
        "GET", f"/api/v1/spotify/status/{account_id}",
        account_id=account_id,
    )


@_rpc_register("GET", "/api/v1/spotify/profile/{user_id}")
async def _rpc_spotify_profile(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """Proxy GET /api/v1/spotify/profile/{user_id} to FastSearch."""
    account_id, err = _resolve_and_auth(kw)
    if err:
        return err
    return await _fastsearch_proxy(
        "GET", f"/api/v1/spotify/profile/{account_id}",
        account_id=account_id,
    )


@_rpc_register("POST", "/api/v1/spotify/disconnect/{user_id}")
async def _rpc_spotify_disconnect(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """Proxy POST /api/v1/spotify/disconnect/{user_id} to FastSearch."""
    account_id, err = _resolve_and_auth(kw)
    if err:
        return err
    return await _fastsearch_proxy(
        "POST", f"/api/v1/spotify/disconnect/{account_id}",
        account_id=account_id,
    )


@_rpc_register("POST", "/api/v1/spotify/rescrape/{user_id}")
async def _rpc_spotify_rescrape(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """Proxy POST /api/v1/spotify/rescrape/{user_id} to FastSearch."""
    account_id, err = _resolve_and_auth(kw)
    if err:
        return err
    return await _fastsearch_proxy(
        "POST", f"/api/v1/spotify/rescrape/{account_id}",
        account_id=account_id,
    )


# ── HTTP callback endpoint (not RPC — browser redirect) ──────────────

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode

callback_router = APIRouter()

# In-memory token store – survives until server restart.
# Key: account_id, value: dict with tokens + profile info.
_spotify_store: dict[int, dict[str, Any]] = {}

_SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
_SPOTIFY_CLIENT_SECRET = os.environ.get(
    "SPOTIFY_CLIENT_SECRET", "",
).strip()
_SPOTIFY_REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI", "").strip()

_UWU_SITE_URL = os.environ.get(
    "AIRUNNER_SITE_URL", "http://localhost:5173",
).strip().rstrip("/")


@callback_router.get("/callback")
async def spotify_oauth_callback(request: Request) -> RedirectResponse:
    """Handle the OAuth redirect from Spotify.

    Validates the state JWT, exchanges the authorization code for
    tokens, fetches the Spotify user profile, and stores everything
    locally.  Redirects the browser back to the UWU client.
    """
    error = request.query_params.get("error")
    code = request.query_params.get("code")
    state = request.query_params.get("state", "")

    params: dict[str, str] = {"spotify": "error"}

    # User denied or error from Spotify
    if error or not code:
        params["reason"] = error or "access_denied"
        return _redirect_to_uwu(params)

    # Validate state JWT
    state_payload = _verify_state(state)
    if state_payload is None:
        params["reason"] = "invalid_state"
        return _redirect_to_uwu(params)

    user_id = state_payload["user_id"]
    code_verifier = state_payload["code_verifier"]

    # Exchange code for tokens
    tokens = _exchange_code(code, code_verifier, user_id)
    if not tokens:
        params["reason"] = "token_exchange_failed"
        return _redirect_to_uwu(params)

    # Fetch profile info
    profile_info = _fetch_spotify_profile(tokens["access_token"])
    if not profile_info:
        params["reason"] = "profile_fetch_failed"
        return _redirect_to_uwu(params)

    # Store everything locally
    _spotify_store[user_id] = {
        "connected": True,
        "spotify_user_id": profile_info.get("id", ""),
        "display_name": profile_info.get("display_name"),
        "spotify_image_url": (
            profile_info.get("images", [{}])[0].get("url")
            if profile_info.get("images")
            else None
        ),
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at": (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=tokens.get("expires_in", 3600))
        ).isoformat(),
        "connected_at": datetime.datetime.now(
            datetime.timezone.utc,
        ).isoformat(),
    }

    logger.info(
        "Spotify OAuth success: user_id=%d spotify=%s",
        user_id,
        profile_info.get("id"),
    )

    params = {"spotify": "connected"}
    return _redirect_to_uwu(params)


def _redirect_to_uwu(params: dict[str, str]) -> RedirectResponse:
    """Redirect back to the UWU client settings page."""
    qs = urlencode(params)
    return RedirectResponse(f"{_UWU_SITE_URL}/settings?{qs}")


def _verify_state(state: str) -> dict[str, Any] | None:
    """Validate the OAuth state JWT."""
    if not _STATE_SECRET:
        logger.error("SPOTIFY_STATE_JWT_SECRET not configured")
        return None
    try:
        payload = jwt.decode(
            state,
            _STATE_SECRET,
            algorithms=[_STATE_ALGORITHM],
            options={
                "require": ["user_id", "code_verifier", "iat", "exp"],
                "verify_exp": True,
            },
        )
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        if payload.get("iat", 0) > now + 300:
            logger.warning("state JWT iat too far in the future")
            return None
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Expired state JWT")
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid state JWT: %s", exc)
    return None


def _exchange_code(
    code: str, code_verifier: str, user_id: int,
) -> dict[str, Any] | None:
    """Exchange an authorization code for access/refresh tokens."""
    if not _SPOTIFY_CLIENT_ID or not _SPOTIFY_CLIENT_SECRET:
        logger.error(
            "SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET not set",
        )
        return None
    redirect_uri = _SPOTIFY_REDIRECT_URI or _build_redirect_uri()
    try:
        resp = _requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": _SPOTIFY_CLIENT_ID,
                "code_verifier": code_verifier,
            },
            auth=(_SPOTIFY_CLIENT_ID, _SPOTIFY_CLIENT_SECRET),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error(
            "Spotify token exchange failed for user_id=%d: %s",
            user_id, exc,
        )
        return None


def _fetch_spotify_profile(
    access_token: str,
) -> dict[str, Any] | None:
    """Fetch the Spotify user profile."""
    try:
        resp = _requests.get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Failed to fetch Spotify profile: %s", exc)
        return None


def _build_redirect_uri() -> str:
    """Build the redirect URI pointing to this server."""
    return f"{_INSTANCE_URL.rstrip('/')}/api/v1/spotify/callback"
