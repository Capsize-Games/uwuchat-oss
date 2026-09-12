"""WebSocket RPC handlers for email account linking / unlinking.

Mirrors the HTTP routes in ``routes.py`` — split into its own module
to keep both files under the project's line-count limit.
"""

from __future__ import annotations

import asyncio
from typing import Any

from airunner_services.api.routes.events import _rpc_register
from airunner_services.api.ws_tenant import resolve_ws_tenant, ws_dek_scope


def _rpc_auth(kw: dict) -> tuple[int | None, int]:
    """Resolve WS tenant + user_id, returning (account_id, user_id)."""
    ws = kw.get("ws")
    if ws is None:
        return None, 0
    _tenant, account_id = resolve_ws_tenant(ws)
    path_params = kw.get("path_params", {})
    user_id = int(path_params.get("user_id", 0))
    return account_id, user_id


@_rpc_register("POST", "/api/v1/email/connect/{user_id}")
async def _rpc_email_connect(body: dict, **kw: Any) -> dict[str, Any]:
    """RPC handler for email connect."""
    from .routes import (
        EMAIL_CONNECT_DISABLED,
        EMAIL_CONNECT_DISABLED_MESSAGE,
        _do_connect,
    )
    from ._route_helpers import validate_fastmail_token

    if EMAIL_CONNECT_DISABLED:
        return {
            "status": 503,
            "body": {"error": EMAIL_CONNECT_DISABLED_MESSAGE},
        }

    account_id, user_id = _rpc_auth(kw)
    if account_id is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}
    if account_id != user_id:
        return {"status": 403, "body": {"error": "Forbidden"}}

    token = (body.get("token") or "").strip()
    email = (body.get("email_address") or "").strip()
    if not token or not email:
        return {"status": 400, "body": {"error": "token and email_address required"}}

    validated = await validate_fastmail_token(token)
    if validated is None:
        return {"status": 401, "body": {"error": "Invalid Fastmail API token"}}

    with ws_dek_scope(account_id):
        _, result = await asyncio.to_thread(
            _do_connect, user_id, token, validated,
        )
    return {"status": 200, "body": result}


@_rpc_register("GET", "/api/v1/email/status/{user_id}")
async def _rpc_email_status(body: dict, **kw: Any) -> dict[str, Any]:
    """RPC handler for email connection status."""
    from .routes import _do_status

    account_id, user_id = _rpc_auth(kw)
    if account_id is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}
    if account_id != user_id:
        return {"status": 403, "body": {"error": "Forbidden"}}
    with ws_dek_scope(account_id):
        status = await asyncio.to_thread(_do_status, user_id)
    return {"status": 200, "body": status}


@_rpc_register("POST", "/api/v1/email/disconnect/{user_id}")
async def _rpc_email_disconnect(body: dict, **kw: Any) -> dict[str, Any]:
    """RPC handler for email disconnect."""
    from .routes import _do_disconnect

    account_id, user_id = _rpc_auth(kw)
    if account_id is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}
    if account_id != user_id:
        return {"status": 403, "body": {"error": "Forbidden"}}
    with ws_dek_scope(account_id):
        result = await asyncio.to_thread(_do_disconnect, user_id)
    return {"status": 200, "body": result}


@_rpc_register("GET", "/api/v1/email/sync-progress/{user_id}")
async def _rpc_email_sync_progress(body: dict, **kw: Any) -> dict[str, Any]:
    """RPC handler for live email-sync progress."""
    from .routes import _do_sync_progress

    account_id, user_id = _rpc_auth(kw)
    if account_id is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}
    if account_id != user_id:
        return {"status": 403, "body": {"error": "Forbidden"}}
    result = await asyncio.to_thread(_do_sync_progress, user_id)
    return {"status": 200, "body": result}
