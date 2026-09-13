"""itch.io integration — OAuth auth + local storage."""

from __future__ import annotations

import datetime
import json as _json
import logging
import os
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from airunner_services.api.routes.events import _rpc_register
from airunner_services.api.ws_tenant import resolve_ws_tenant
from airunner_services.database.models.itch_connection import ItchConnection
from airunner_services.database.session import session_scope
from extensions.auth.server.dependencies import require_auth
from projects.uwuchat.server.steam._proxy import (
    require_self,
    require_ws_auth,
)

from ._api import build_oauth_url, get_owned_games, get_profile

logger = logging.getLogger(__name__)

router = APIRouter()

# ---- Configuration -------------------------------------------------------

_JWT_SECRET = (
    os.environ.get("ITCHIO_STATE_JWT_SECRET", "").strip()
    or os.environ.get("AIRUNNER_JWT_SECRET", "").strip()
)
_JWT_ALGORITHM = "HS256"
_JWT_TTL_SECONDS = int(os.environ.get("ITCHIO_STATE_TTL", "600"))

_INSTANCE_URL = os.environ.get(
    "AIRUNNER_SITE_URL", "http://localhost:5173",
).strip().rstrip("/")

# ---------------------------------------------------------------------------


def _itch_state_jwt(account_id: int) -> str | None:
    """Sign a short-lived state JWT for itch.io OAuth."""
    if not _JWT_SECRET:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "account_id": account_id,
        "iat": now,
        "exp": now + datetime.timedelta(seconds=_JWT_TTL_SECONDS),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def _decode_itch_state(state: str) -> int | None:
    """Decode an itch.io state JWT → account_id, or None."""
    try:
        payload = jwt.decode(
            state, _JWT_SECRET, algorithms=[_JWT_ALGORITHM],
        )
        return int(payload["account_id"])
    except Exception:
        return None


def _connection_to_dict(conn: ItchConnection) -> dict[str, Any]:
    """Convert an ItchConnection ORM instance to the API response shape."""

    def _parse_json(val: str | None) -> list | None:
        if not val:
            return None
        try:
            return _json.loads(val)
        except (ValueError, TypeError):
            return None

    return {
        "connected": True,
        "status": conn.status,
        "itch_user_id": conn.itch_user_id,
        "username": conn.username,
        "display_name": conn.display_name,
        "cover_url": conn.cover_url,
        "profile_url": conn.profile_url,
        "owned_games": _parse_json(conn.owned_games_json) or [],
        "last_scraped_at": (
            conn.last_scraped_at.isoformat()
            if conn.last_scraped_at
            else None
        ),
        "error": conn.error,
    }


# ---- OAuth Auth Routes ---------------------------------------------------


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/auth/login")
async def itch_auth_login(
    request: Request,
) -> dict[str, Any]:
    """Return the itch.io OAuth login URL with a signed state JWT."""
    if not _JWT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="itch.io integration is not configured.",
        )

    account_id = await require_auth(request)
    state = _itch_state_jwt(account_id)
    if state is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate state token.",
        )

    return {"url": build_oauth_url(state)}


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/auth/callback")
async def itch_auth_callback(
    request: Request,
) -> RedirectResponse:
    """Receive OAuth token via POST body, fetch + store data.

    The token is sent in the POST body by the frontend callback page
    so it never appears in server/proxy access logs as a URL query
    parameter.
    """
    settings_url = f"{_INSTANCE_URL}/settings?tab=integrations"

    try:
        body = await request.json()
    except Exception:
        logger.warning("itch.io callback: invalid JSON body")
        return RedirectResponse(
            url=f"{settings_url}&itch_error=invalid_body",
            status_code=302,
        )

    state = (body.get("state") or "").strip()
    if not state:
        logger.warning("itch.io callback missing state")
        return RedirectResponse(
            url=f"{settings_url}&itch_error=invalid_state",
            status_code=302,
        )

    account_id = _decode_itch_state(state)
    if account_id is None:
        logger.warning("Invalid or expired itch.io state JWT")
        return RedirectResponse(
            url=f"{settings_url}&itch_error=invalid_state",
            status_code=302,
        )

    token = (body.get("access_token") or "").strip()
    if not token:
        logger.warning("itch.io callback missing access_token")
        return RedirectResponse(
            url=f"{settings_url}&itch_error=no_token",
            status_code=302,
        )

    user = await get_profile(token)
    if user is None:
        return RedirectResponse(
            url=f"{settings_url}&itch_error=fetch_failed",
            status_code=302,
        )

    games = await get_owned_games(token)

    # Look up tenant schema
    tenant_schema: str | None = None
    try:
        from airunner_services.database.session import public_session_scope
        from extensions.auth.server.models import Account
        with public_session_scope() as psession:
            acct = psession.query(Account).filter(
                Account.id == account_id,
            ).first()
            if acct:
                tenant_schema = acct.tenant_schema
    except Exception as exc:
        logger.warning("Tenant lookup for itch.io failed: %s", exc)

    if not tenant_schema:
        return RedirectResponse(
            url=f"{settings_url}&itch_error=tenant_not_found",
            status_code=302,
        )

    from airunner_services.data.tenant import (
        reset_tenant_key,
        set_tenant_key,
        tenant_key_from_schema,
    )
    tenant_key = tenant_key_from_schema(tenant_schema)
    if not tenant_key:
        return RedirectResponse(
            url=f"{settings_url}&itch_error=tenant_not_found",
            status_code=302,
        )

    ttoken = set_tenant_key(tenant_key)
    try:
        with session_scope() as session:
            existing = session.query(ItchConnection).filter(
                ItchConnection.account_id == account_id,
            ).first()
            if existing:
                existing.itch_user_id = user.get("id")
                existing.username = user.get("username")
                existing.display_name = user.get("display_name")
                existing.cover_url = user.get("cover_url")
                existing.profile_url = user.get("url")
                existing.owned_games_json = _json.dumps(games)
                existing.last_scraped_at = datetime.datetime.utcnow()
                existing.error = None
            else:
                conn = ItchConnection(
                    account_id=account_id,
                    itch_user_id=user.get("id"),
                    username=user.get("username"),
                    display_name=user.get("display_name"),
                    cover_url=user.get("cover_url"),
                    profile_url=user.get("url"),
                    owned_games_json=_json.dumps(games),
                    last_scraped_at=datetime.datetime.utcnow(),
                )
                session.add(conn)
            session.commit()
            logger.info(
                "itch.io data stored for account_id=%s (%d games)",
                account_id, len(games),
            )
    except Exception as exc:
        logger.warning("Failed to store itch.io data: %s", exc)
        return RedirectResponse(
            url=f"{settings_url}&itch_error=store_failed",
            status_code=302,
        )
    finally:
        reset_tenant_key(ttoken)

    return RedirectResponse(
        url=f"{settings_url}&itch_connected=1", status_code=302,
    )


# ---- Status / Profile / Disconnect ---------------------------------------


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/status/{user_id}")
async def itch_status_http(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """HTTP GET handler for itch.io connection status."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        with session_scope() as session:
            conn = session.query(ItchConnection).filter(
                ItchConnection.account_id == user_id,
            ).first()
            if conn is None:
                return {
                    "connected": False,
                    "status": "not_connected",
                    "itch_user_id": None,
                    "username": None,
                    "display_name": None,
                    "cover_url": None,
                    "profile_url": None,
                    "owned_games": [],
                    "last_scraped_at": None,
                    "error": None,
                }
            return _connection_to_dict(conn)
    except Exception as exc:
        logger.warning("itch.io status query failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to query itch.io connection status",
        ) from exc


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/profile/{user_id}")
async def itch_profile_http(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """HTTP GET handler for itch.io profile info."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        with session_scope() as session:
            conn = session.query(ItchConnection).filter(
                ItchConnection.account_id == user_id,
            ).first()
            if conn is None:
                raise HTTPException(
                    status_code=404,
                    detail="No itch.io account connected",
                )
            return _connection_to_dict(conn)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("itch.io profile query failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to query itch.io profile",
        ) from exc


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/disconnect/{user_id}")
async def itch_disconnect_http(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """HTTP POST handler for disconnecting itch.io."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        with session_scope() as session:
            conn = session.query(ItchConnection).filter(
                ItchConnection.account_id == user_id,
            ).first()
            if conn is not None:
                session.delete(conn)
                session.commit()
        return {"success": True}
    except Exception as exc:
        logger.warning("itch.io disconnect failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to disconnect itch.io",
        ) from exc


# ---- RPC Handlers --------------------------------------------------------


@_rpc_register("GET", "/api/v1/itch/status/{user_id}")
async def _rpc_itch_status(body: dict, **kw: Any) -> dict[str, Any]:
    """RPC handler for itch.io connection status."""
    _ws, aid, err = require_ws_auth(kw)
    if err:
        return err

    try:
        with session_scope() as session:
            conn = session.query(ItchConnection).filter(
                ItchConnection.account_id == aid,
            ).first()
            if conn is None:
                return {
                    "status": 200,
                    "body": {
                        "connected": False,
                        "status": "not_connected",
                        "itch_user_id": None,
                        "username": None,
                        "display_name": None,
                        "cover_url": None,
                        "profile_url": None,
                        "owned_games": [],
                        "last_scraped_at": None,
                        "error": None,
                    },
                }
            return {"status": 200, "body": _connection_to_dict(conn)}
    except Exception as exc:
        logger.warning("itch.io RPC status failed: %s", exc)
        return {
            "status": 500,
            "body": {"error": "Failed to query itch.io connection status"},
        }


@_rpc_register("GET", "/api/v1/itch/profile/{user_id}")
async def _rpc_itch_profile(body: dict, **kw: Any) -> dict[str, Any]:
    """RPC handler for itch.io profile."""
    _ws, aid, err = require_ws_auth(kw)
    if err:
        return err

    try:
        with session_scope() as session:
            conn = session.query(ItchConnection).filter(
                ItchConnection.account_id == aid,
            ).first()
            if conn is None:
                return {
                    "status": 404,
                    "body": {"error": "No itch.io account connected"},
                }
            return {"status": 200, "body": _connection_to_dict(conn)}
    except Exception as exc:
        logger.warning("itch.io RPC profile failed: %s", exc)
        return {
            "status": 500,
            "body": {"error": "Failed to query itch.io profile"},
        }


@_rpc_register("POST", "/api/v1/itch/disconnect/{user_id}")
async def _rpc_itch_disconnect(body: dict, **kw: Any) -> dict[str, Any]:
    """RPC handler for disconnecting itch.io."""
    _ws, aid, err = require_ws_auth(kw)
    if err:
        return err
    path_params = kw.get("path_params", {})
    err2 = require_self(aid, path_params, "user_id")
    if err2:
        return err2

    try:
        with session_scope() as session:
            conn = session.query(ItchConnection).filter(
                ItchConnection.account_id == aid,
            ).first()
            if conn is not None:
                session.delete(conn)
                session.commit()
        return {"status": 200, "body": {"success": True}}
    except Exception as exc:
        logger.warning("itch.io RPC disconnect failed: %s", exc)
        return {
            "status": 500,
            "body": {"error": "Failed to disconnect itch.io"},
        }


@_rpc_register("GET", "/api/v1/itch/auth/login")
async def _rpc_itch_auth_login(body: dict, **kw: Any) -> dict[str, Any]:
    """RPC handler for itch.io auth login URL."""
    ws = kw.get("ws")
    if ws is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}

    _tenant, account_id = resolve_ws_tenant(ws)
    if account_id is None:
        return {
            "status": 401,
            "body": {"error": "Authentication required"},
        }

    state = _itch_state_jwt(account_id)
    if state is None:
        return {
            "status": 500,
            "body": {"error": "Failed to generate state token"},
        }

    return {"status": 200, "body": {"url": build_oauth_url(state)}}
