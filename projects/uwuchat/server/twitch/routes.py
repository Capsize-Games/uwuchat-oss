"""Twitch integration — OAuth linking + local storage."""

from __future__ import annotations

import datetime
import logging
import os
from typing import Any
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from airunner_services.api.routes.events import _rpc_register
from airunner_services.api.ws_tenant import resolve_ws_tenant
from airunner_services.database.models.twitch_connection import (
    TwitchConnection,
)
from airunner_services.database.session import session_scope
from extensions.auth.server.dependencies import require_auth

logger = logging.getLogger(__name__)

router = APIRouter()

# ---- Configuration -------------------------------------------------------

_CLIENT_ID = os.environ.get("AIRUNNER_TWITCH_CLIENT_ID", "").strip()
_CLIENT_SECRET = os.environ.get(
    "AIRUNNER_TWITCH_CLIENT_SECRET", "",
).strip()
_JWT_SECRET = (
    os.environ.get("TWITCH_STATE_JWT_SECRET", "").strip()
    or os.environ.get("AIRUNNER_JWT_SECRET", "").strip()
)
_JWT_ALGORITHM = "HS256"
_JWT_TTL_SECONDS = int(os.environ.get("TWITCH_STATE_TTL", "600"))
_CONFIGURED = bool(_CLIENT_ID and _CLIENT_SECRET and _JWT_SECRET)

_INSTANCE_URL = os.environ.get(
    "AIRUNNER_SITE_URL", "http://localhost:5173",
).strip().rstrip("/")

_TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
_TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_TWITCH_HELIX_USERS = "https://api.twitch.tv/helix/users"

# Scopes for linking
_LINK_SCOPES = ["user:read:email"]


# ---- State JWT helpers ---------------------------------------------------


def _state_jwt(
    account_id: int, mode: str = "link",
) -> str | None:
    """Generate a short-lived JWT for the Twitch OAuth state parameter."""
    if not _JWT_SECRET:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "user_id": account_id,
        "mode": mode,
        "iat": now,
        "exp": now + datetime.timedelta(seconds=_JWT_TTL_SECONDS),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def _decode_state_jwt(
    state: str,
) -> tuple[int | None, str]:
    """Decode a Twitch state JWT, returning ``(user_id, mode)``."""
    try:
        payload = jwt.decode(
            state, _JWT_SECRET, algorithms=[_JWT_ALGORITHM],
        )
        return int(payload["user_id"]), payload.get("mode", "link")
    except Exception:
        return None, "link"


# ---- Connection helpers --------------------------------------------------


def _connection_to_dict(
    conn: TwitchConnection,
) -> dict[str, Any]:
    """Convert a TwitchConnection ORM instance to the API response shape."""
    return {
        "connected": True,
        "status": conn.status,
        "twitch_id": conn.twitch_id,
        "display_name": conn.display_name,
        "avatar_url": conn.avatar_url,
        "description": conn.description,
        "last_scraped_at": (
            conn.last_scraped_at.isoformat()
            if conn.last_scraped_at
            else None
        ),
        "error": conn.error,
    }


# ---- Token exchange helpers ----------------------------------------------


async def _exchange_code(
    code: str,
) -> tuple[str | None, dict | None, str | None]:
    """Exchange OAuth code for an access token and user info.

    Returns ``(access_token, user_dict, error_msg)`` — exactly one of
    *user_dict* or *error_msg* is not None.
    """
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            # Exchange code for tokens
            token_resp = await client.post(
                _TWITCH_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": _CLIENT_ID,
                    "client_secret": _CLIENT_SECRET,
                    "redirect_uri": (
                        f"{_INSTANCE_URL}/api/v1/twitch/auth/callback"
                    ),
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            tokens = token_resp.json()
            access_token = tokens.get("access_token")
            if not access_token:
                return None, None, "No access token in response"

            # Fetch user info from Helix
            user_resp = await client.get(
                _TWITCH_HELIX_USERS,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Client-Id": _CLIENT_ID,
                },
            )
            user_resp.raise_for_status()
            user_data = user_resp.json()
            users = user_data.get("data", [])
            if not users:
                return None, None, "No user data from Twitch"
            return access_token, users[0], None
    except Exception as exc:
        logger.warning("Twitch OAuth exchange failed: %s", exc)
        return None, None, str(exc)


# ---- OAuth Routes --------------------------------------------------------


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/auth/login")
async def twitch_auth_login(
    request: Request,
    mode: str = Query("link"),
) -> dict[str, Any]:
    """Return the Twitch OAuth URL with a signed state JWT.

    *mode*:
      ``"link"`` — link Twitch to the authenticated account (default).
      ``"auth"`` — sign in / sign up with Twitch (uses auth extension).
    """
    if not _CONFIGURED:
        raise HTTPException(
            status_code=503,
            detail=(
                "Twitch integration is not configured. "
                "Set AIRUNNER_TWITCH_CLIENT_ID and "
                "AIRUNNER_TWITCH_CLIENT_SECRET to enable."
            ),
        )

    if mode == "auth":
        # Auth-mode is handled by the auth extension's Twitch OAuth routes.
        # Redirect the client there instead.
        return {"url": "/api/v1/auth/oauth/twitch/login"}

    # Link mode — require authentication.
    account_id = await require_auth(request)

    state = _state_jwt(account_id, mode=mode)
    if state is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate state token.",
        )

    callback_url = f"{_INSTANCE_URL}/api/v1/twitch/auth/callback"
    params = {
        "client_id": _CLIENT_ID,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": " ".join(_LINK_SCOPES),
        "state": state,
        "force_verify": "true",
    }
    return {"url": f"{_TWITCH_AUTH_URL}?{urlencode(params)}"}


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/auth/callback")
async def twitch_auth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(""),
) -> RedirectResponse:
    """Handle the Twitch OAuth callback.

    Decodes the state JWT to determine whether this is a link or auth
    flow, exchanges the code, and stores/updates the connection.
    """
    site_url = _INSTANCE_URL
    settings_url = f"{site_url}/settings?tab=integrations"
    login_url = f"{site_url}/login"

    jwt_account_id, jwt_mode = _decode_state_jwt(state)

    # ---- Link mode: attach Twitch to existing account ---- ---------------
    if jwt_mode == "link" and jwt_account_id is not None:
        _access_token, user, err = await _exchange_code(code)
        if err or user is None:
            return RedirectResponse(
                url=f"{settings_url}&twitch_error=exchange_failed",
                status_code=302,
            )

        twitch_id = str(user.get("id", ""))
        display_name = user.get("display_name", "")
        avatar_url = user.get("profile_image_url", "")
        email = user.get("email", "")
        description = user.get("description", "")

        if not twitch_id:
            return RedirectResponse(
                url=f"{settings_url}&twitch_error=no_twitch_id",
                status_code=302,
            )

        try:
            with session_scope() as session:
                existing = session.query(TwitchConnection).filter(
                    TwitchConnection.account_id == jwt_account_id,
                ).first()
                if existing:
                    existing.twitch_id = twitch_id
                    existing.display_name = display_name
                    existing.avatar_url = avatar_url
                    existing.email = email
                    existing.description = description
                    existing.error = None
                else:
                    conn = TwitchConnection(
                        account_id=jwt_account_id,
                        twitch_id=twitch_id,
                        display_name=display_name,
                        avatar_url=avatar_url,
                        email=email,
                        description=description,
                    )
                    session.add(conn)
                session.commit()
        except Exception as exc:
            logger.warning("Failed to store Twitch connection: %s", exc)
            return RedirectResponse(
                url=f"{settings_url}&twitch_error=connect_failed",
                status_code=302,
            )

        return RedirectResponse(
            url=f"{settings_url}&twitch_connected=1", status_code=302,
        )

    # ---- Auth mode not handled here — delegate to auth extension ----------
    return RedirectResponse(
        url=f"{login_url}?error=twitch_auth_failed",
        status_code=302,
    )


# ---- RPC Handlers --------------------------------------------------------


@_rpc_register("GET", "/api/v1/twitch/auth/login")
async def _rpc_twitch_auth_login(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """RPC handler for ``GET /api/v1/twitch/auth/login``."""
    ws = kw.get("ws")
    if ws is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}

    _tenant, account_id = resolve_ws_tenant(ws)
    if account_id is None:
        return {
            "status": 401,
            "body": {"error": "Authentication required"},
        }

    if not _CONFIGURED:
        return {
            "status": 503,
            "body": {
                "error": (
                    "Twitch integration is not configured. "
                    "Set AIRUNNER_TWITCH_CLIENT_ID and "
                    "AIRUNNER_TWITCH_CLIENT_SECRET to enable."
                ),
            },
        }

    state = _state_jwt(account_id)
    if state is None:
        return {
            "status": 500,
            "body": {"error": "Failed to generate state token."},
        }

    callback_url = f"{_INSTANCE_URL}/api/v1/twitch/auth/callback"
    params = {
        "client_id": _CLIENT_ID,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": " ".join(_LINK_SCOPES),
        "state": state,
        "force_verify": "true",
    }
    return {
        "status": 200,
        "body": {"url": f"{_TWITCH_AUTH_URL}?{urlencode(params)}"},
    }


# ---- HTTP Status / Profile / Disconnect Routes ---------------------------


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/status/{user_id}")
async def twitch_status_http(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """HTTP GET handler for Twitch connection status."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        with session_scope() as session:
            conn = session.query(TwitchConnection).filter(
                TwitchConnection.account_id == user_id,
            ).first()
            if conn is None:
                return {
                    "connected": False,
                    "status": "not_connected",
                    "twitch_id": None,
                    "display_name": None,
                    "avatar_url": None,
                    "description": None,
                    "last_scraped_at": None,
                    "error": None,
                }
            return _connection_to_dict(conn)
    except Exception as exc:
        logger.warning("Twitch status HTTP query failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to query Twitch connection status",
        ) from exc


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/profile/{user_id}")
async def twitch_profile_http(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """HTTP GET handler for Twitch profile info."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        with session_scope() as session:
            conn = session.query(TwitchConnection).filter(
                TwitchConnection.account_id == user_id,
            ).first()
            if conn is None:
                raise HTTPException(
                    status_code=404,
                    detail="No Twitch account connected",
                )
            return _connection_to_dict(conn)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Twitch profile HTTP query failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to query Twitch profile",
        ) from exc


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/schedule/{user_id}")
async def twitch_schedule_http(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """HTTP GET handler for Twitch channel schedule."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        with session_scope() as session:
            conn = session.query(TwitchConnection).filter(
                TwitchConnection.account_id == user_id,
            ).first()
            if conn is None:
                raise HTTPException(
                    status_code=404,
                    detail="No Twitch account connected",
                )

            twitch_id = conn.twitch_id

        # Fetch schedule from Twitch API
        from ._webapi import get_channel_schedule

        schedule_data = await get_channel_schedule(twitch_id)
        if schedule_data is None:
            return {
                "broadcaster_id": twitch_id,
                "segments": [],
                "error": "Failed to fetch schedule",
            }

        segments = schedule_data.get("segments") or []
        broadcaster = schedule_data.get("broadcaster", {})

        return {
            "broadcaster_id": broadcaster.get("id", twitch_id),
            "broadcaster_name": broadcaster.get("login", ""),
            "broadcaster_display_name": broadcaster.get("display_name", ""),
            "segments": [
                {
                    "id": seg.get("id", ""),
                    "start_time": seg.get("start_time", ""),
                    "end_time": seg.get("end_time", ""),
                    "title": seg.get("title", ""),
                    "category": seg.get("category", {}),
                    "is_recurring": seg.get("is_recurring", False),
                    "canceled_until": seg.get("canceled_until"),
                }
                for seg in segments
            ],
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Twitch schedule HTTP query failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to query Twitch schedule",
        ) from exc


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/disconnect/{user_id}")
async def twitch_disconnect_http(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """HTTP POST handler for disconnecting Twitch."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        with session_scope() as session:
            conn = session.query(TwitchConnection).filter(
                TwitchConnection.account_id == user_id,
            ).first()
            if conn is None:
                raise HTTPException(
                    status_code=404,
                    detail="No Twitch account connected",
                )
            session.delete(conn)
            session.commit()
            return {"message": "Twitch account disconnected"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Twitch disconnect HTTP failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to disconnect Twitch account",
        ) from exc


# ---- RPC Status / Profile / Disconnect Handlers --------------------------


@_rpc_register("GET", "/api/v1/twitch/status/{user_id}")
async def _rpc_twitch_status(body: dict, **kw: Any) -> dict[str, Any]:
    """Return Twitch connection status from the local database."""
    ws = kw.get("ws")
    if ws is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}
    _tenant, aid = resolve_ws_tenant(ws)
    if aid is None:
        return {
            "status": 401,
            "body": {"error": "Authentication required"},
        }

    try:
        with session_scope() as session:
            conn = session.query(TwitchConnection).filter(
                TwitchConnection.account_id == aid,
            ).first()
            if conn is None:
                return {
                    "status": 200,
                    "body": {
                        "connected": False,
                        "status": "not_connected",
                        "twitch_id": None,
                        "display_name": None,
                        "avatar_url": None,
                        "description": None,
                        "last_scraped_at": None,
                        "error": None,
                    },
                }
            return {"status": 200, "body": _connection_to_dict(conn)}
    except Exception as exc:
        logger.warning("Twitch status query failed: %s", exc)
        return {
            "status": 500,
            "body": {"error": "Failed to query Twitch connection status"},
        }


@_rpc_register("GET", "/api/v1/twitch/profile/{user_id}")
async def _rpc_twitch_profile(body: dict, **kw: Any) -> dict[str, Any]:
    """Return Twitch connection info."""
    ws = kw.get("ws")
    if ws is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}
    _tenant, aid = resolve_ws_tenant(ws)
    if aid is None:
        return {
            "status": 401,
            "body": {"error": "Authentication required"},
        }

    try:
        with session_scope() as session:
            conn = session.query(TwitchConnection).filter(
                TwitchConnection.account_id == aid,
            ).first()
            if conn is None:
                return {
                    "status": 404,
                    "body": {"error": "No Twitch account connected"},
                }
            return {"status": 200, "body": _connection_to_dict(conn)}
    except Exception as exc:
        logger.warning("Twitch profile query failed: %s", exc)
        return {
            "status": 500,
            "body": {"error": "Failed to query Twitch profile"},
        }


@_rpc_register("GET", "/api/v1/twitch/schedule/{user_id}")
async def _rpc_twitch_schedule(body: dict, **kw: Any) -> dict[str, Any]:
    """Return Twitch channel schedule."""
    ws = kw.get("ws")
    if ws is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}
    _tenant, aid = resolve_ws_tenant(ws)
    if aid is None:
        return {
            "status": 401,
            "body": {"error": "Authentication required"},
        }

    try:
        with session_scope() as session:
            conn = session.query(TwitchConnection).filter(
                TwitchConnection.account_id == aid,
            ).first()
            if conn is None:
                return {
                    "status": 404,
                    "body": {"error": "No Twitch account connected"},
                }

            twitch_id = conn.twitch_id

        from ._webapi import get_channel_schedule

        schedule_data = await get_channel_schedule(twitch_id)
        if schedule_data is None:
            return {
                "status": 200,
                "body": {
                    "broadcaster_id": twitch_id,
                    "segments": [],
                },
            }

        segments = schedule_data.get("segments") or []
        broadcaster = schedule_data.get("broadcaster", {})

        return {
            "status": 200,
            "body": {
                "broadcaster_id": broadcaster.get("id", twitch_id),
                "broadcaster_name": broadcaster.get("login", ""),
                "broadcaster_display_name": broadcaster.get(
                    "display_name", "",
                ),
                "segments": [
                    {
                        "id": seg.get("id", ""),
                        "start_time": seg.get("start_time", ""),
                        "end_time": seg.get("end_time", ""),
                        "title": seg.get("title", ""),
                        "category": seg.get("category", {}),
                        "is_recurring": seg.get("is_recurring", False),
                        "canceled_until": seg.get("canceled_until"),
                    }
                    for seg in segments
                ],
            },
        }
    except Exception as exc:
        logger.warning("Twitch schedule query failed: %s", exc)
        return {
            "status": 500,
            "body": {"error": "Failed to query Twitch schedule"},
        }


@_rpc_register("POST", "/api/v1/twitch/disconnect/{user_id}")
async def _rpc_twitch_disconnect(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """Remove the Twitch connection from the local database."""
    ws = kw.get("ws")
    if ws is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}
    _tenant, aid = resolve_ws_tenant(ws)
    if aid is None:
        return {
            "status": 401,
            "body": {"error": "Authentication required"},
        }
    path_params = kw.get("path_params", {})
    raw = path_params.get("user_id", "")
    try:
        target_id = int(raw)
    except (ValueError, TypeError):
        return {"status": 400, "body": {"error": "Invalid user_id"}}
    if target_id != aid:
        return {"status": 403, "body": {"error": "Forbidden"}}

    try:
        with session_scope() as session:
            conn = session.query(TwitchConnection).filter(
                TwitchConnection.account_id == aid,
            ).first()
            if conn is None:
                return {
                    "status": 404,
                    "body": {"error": "No Twitch account connected"},
                }
            session.delete(conn)
            session.commit()
            return {
                "status": 200,
                "body": {"message": "Twitch account disconnected"},
            }
    except Exception as exc:
        logger.warning("Twitch disconnect failed: %s", exc)
        return {
            "status": 500,
            "body": {"error": "Failed to disconnect Twitch account"},
        }
