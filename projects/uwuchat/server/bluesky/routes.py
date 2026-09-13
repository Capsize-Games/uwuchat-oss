"""Bluesky integration — App Password flow.

Users connect their Bluesky account by providing their handle and
an app-specific password generated at bsky.social/settings/app-passwords.
Credentials are stored encrypted in User.data.
"""

from __future__ import annotations

import json as _json
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from airunner_services.api.routes.events import _rpc_register
from airunner_services.api.ws_tenant import resolve_ws_tenant
from airunner_services.database.session import session_scope
from airunner_services.utils.error_sanitizer import log_and_sanitize
from extensions.auth.server.dependencies import require_auth

from ._oauth import create_bsky_session, fetch_author_feed

logger = logging.getLogger(__name__)

router = APIRouter()

# ---- Helpers -------------------------------------------------------------


def _get_bluesky_connection(user_id: int) -> dict[str, Any] | None:
    """Read the Bluesky connection data from User.data."""
    try:
        with session_scope() as session:
            from airunner_services.database.models.user import (
                User,
            )
            from airunner_services.data.tenant import get_tenant_key
            tk = get_tenant_key()
            logger.debug(
                "GET CONNECTION user_id=%s tenant_key=%s", user_id, tk,
            )
            user = session.query(User).filter(
                User.id == user_id,
            ).first()
            logger.debug(
                "GET CONNECTION user found: %s", user is not None,
            )
            if user is None or not user.data:
                return None
            data = user.data
            if isinstance(data, str):
                try:
                    data = _json.loads(data)
                except (ValueError, TypeError):
                    return None
            return data.get("bluesky_connection")
    except Exception:
        return None


def _set_bluesky_connection(
    user_id: int,
    connection: dict[str, Any] | None,
) -> None:
    """Write (or remove) the Bluesky connection data in User.data."""
    logger.info(
        "_set_bluesky_connection called: user_id=%s connection=%s",
        user_id, bool(connection),
    )
    with session_scope() as session:
        from airunner_services.database.models.user import (
            User,
        )
        user = session.query(User).filter(
            User.id == user_id,
        ).first()
        logger.info(
            "_set_bluesky_connection user found: %s", user is not None,
        )
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        data = user.data or {}
        if isinstance(data, str):
            try:
                data = _json.loads(data)
            except (ValueError, TypeError):
                data = {}
        if connection is None:
            data.pop("bluesky_connection", None)
        else:
            data["bluesky_connection"] = connection
        user.data = data
        session.commit()
        logger.info(
            "_set_bluesky_connection committed: user_id=%s",
            user_id,
        )


# ---- Routes --------------------------------------------------------------


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/connect/{user_id}")
async def bluesky_connect(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """Connect a Bluesky account using handle + app password.

    Body: { "handle": "user.bsky.social", "app_password": "xxxx-xxxx-xxxx-xxxx" }
    """
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON body",
        ) from None

    handle = (body.get("handle") or "").strip()
    app_password = (body.get("app_password") or "").strip()

    if not handle or not app_password:
        raise HTTPException(
            status_code=400,
            detail="handle and app_password are required",
        )

    session = await create_bsky_session(handle, app_password)
    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid Bluesky credentials",
        )

    connection = {
        "handle": session["handle"],
        "did": session["did"],
    }
    _set_bluesky_connection(user_id, connection)

    return {
        "connected": True,
        "handle": session["handle"],
        "did": session["did"],
    }


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/status/{user_id}")
async def bluesky_status(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """Get Bluesky connection status for a user."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = _get_bluesky_connection(user_id)
    if conn is None:
        return {
            "connected": False,
            "status": "not_connected",
            "handle": None,
            "did": None,
            "error": None,
        }
    return {
        "connected": True,
        "status": "connected",
        "handle": conn.get("handle"),
        "did": conn.get("did"),
        "error": None,
    }


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/posts/{user_id}")
async def bluesky_posts(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """Get recent Bluesky posts for a connected user."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = _get_bluesky_connection(user_id)
    if conn is None:
        return {"posts": [], "handle": None}

    handle = conn.get("handle")
    if not handle:
        return {"posts": [], "handle": None}

    posts = await fetch_author_feed(handle)
    return {"posts": posts, "handle": handle}


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/disconnect/{user_id}")
async def bluesky_disconnect(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """Disconnect Bluesky from a user's profile."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    _set_bluesky_connection(user_id, None)
    return {"success": True}


# ---- WebSocket RPC Handlers ----------------------------------------------
# All client API calls go through the WebSocket RPC channel, not HTTP.
# These decorators mirror the HTTP routes for WS-based invocation.


@_rpc_register("POST", "/api/v1/bluesky/connect/{user_id}")
async def _rpc_bluesky_connect(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """RPC handler for Bluesky connect via app password."""
    try:
        ws = kw.get("ws")
        if ws is None:
            return {"status": 400, "body": {"error": "WebSocket required"}}
        _tenant, account_id = resolve_ws_tenant(ws)
        if account_id is None:
            return {"status": 401, "body": {"error": "Authentication required"}}
        path_params = kw.get("path_params", {})
        user_id = int(path_params.get("user_id", 0))
        if account_id != user_id:
            return {"status": 403, "body": {"error": "Forbidden"}}

        handle = (body.get("handle") or "").strip()
        app_password = (body.get("app_password") or "").strip()
        if not handle or not app_password:
            return {
                "status": 400,
                "body": {"error": "handle and app_password are required"},
            }

        session = await create_bsky_session(handle, app_password)
        if session is None:
            return {
                "status": 401,
                "body": {"error": "Invalid Bluesky credentials"},
            }

        connection = {"handle": session["handle"], "did": session["did"]}
        # Store the connection directly
        logger.debug("STORING BLUESKY CONNECTION for user_id=%s", user_id)
        try:
            with session_scope() as s:
                from airunner_services.database.models.user import (
                    User,
                )
                u = s.query(User).filter(User.id == user_id).first()
                logger.debug("USER FOUND: %s", u is not None)
                if u is not None:
                    from sqlalchemy import text
                    d = u.data or {}
                    if isinstance(d, str):
                        d = _json.loads(d)
                    d["bluesky_connection"] = connection
                    # Use raw SQL to bypass any ORM caching issues
                    s.execute(
                        text("UPDATE users SET data = :data WHERE id = :uid"),
                        {"data": _json.dumps(d), "uid": user_id},
                    )
                    s.commit()
                    logger.debug(
                        "BLUESKY CONNECTION COMMITTED for user %s", user_id,
                    )
        except Exception as exc:
            logger.exception("Failed to store bluesky connection")
            message = log_and_sanitize(
                exc, logger=logger,
                context="bluesky connect store failed",
            )
            return {
                "status": 500,
                "body": {"error": message},
            }

        return {
            "status": 200,
            "body": {
                "connected": True,
                "handle": session["handle"],
                "did": session["did"],
            },
        }
    except Exception as exc:
        logger.exception("Bluesky RPC connect error")
        message = log_and_sanitize(
            exc, logger=logger,
            context="bluesky RPC connect failed",
        )
        return {
            "status": 500,
            "body": {"error": message},
        }


@_rpc_register("GET", "/api/v1/bluesky/status/{user_id}")
async def _rpc_bluesky_status(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """RPC handler for Bluesky connection status."""
    ws = kw.get("ws")
    if ws is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}
    _tenant, account_id = resolve_ws_tenant(ws)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    conn = _get_bluesky_connection(account_id)
    if conn is None:
        return {
            "status": 200,
            "body": {
                "connected": False,
                "status": "not_connected",
                "handle": None,
                "did": None,
                "error": None,
            },
        }
    return {
        "status": 200,
        "body": {
            "connected": True,
            "status": "connected",
            "handle": conn.get("handle"),
            "did": conn.get("did"),
            "error": None,
        },
    }


@_rpc_register("GET", "/api/v1/bluesky/posts/{user_id}")
async def _rpc_bluesky_posts(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """RPC handler for Bluesky posts."""
    ws = kw.get("ws")
    if ws is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}
    _tenant, account_id = resolve_ws_tenant(ws)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    conn = _get_bluesky_connection(account_id)
    if conn is None:
        return {
            "status": 200,
            "body": {"posts": [], "handle": None},
        }
    handle = conn.get("handle")
    if not handle:
        return {
            "status": 200,
            "body": {"posts": [], "handle": None},
        }
    posts = await fetch_author_feed(handle)
    return {
        "status": 200,
        "body": {"posts": posts, "handle": handle},
    }


@_rpc_register("POST", "/api/v1/bluesky/disconnect/{user_id}")
async def _rpc_bluesky_disconnect(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """RPC handler for Bluesky disconnect."""
    ws = kw.get("ws")
    if ws is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}
    _tenant, account_id = resolve_ws_tenant(ws)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    path_params = kw.get("path_params", {})
    user_id = int(path_params.get("user_id", 0))
    if account_id != user_id:
        return {"status": 403, "body": {"error": "Forbidden"}}
    _set_bluesky_connection(user_id, None)
    return {"status": 200, "body": {"success": True}}
