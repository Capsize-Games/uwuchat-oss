"""RPC routes for the UwUchat code-mode toggle.

This app is a "WebSocket-only architecture" (see ``routes/__init__.py``)
— the client's ``request()`` helper sends every call, including plain
GET/PUT, over the shared RPC-over-WebSocket channel, never a real HTTP
request. ``projects/uwuchat/server/routes/code_mode_routes.py`` defines
a matching FastAPI HTTP router, but the client can never reach it; this
module is the actual handler the client's ``codeMode.ts`` talks to.
"""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.api.routes.events_rpc import (
    _rpc_error_response,
    _rpc_register,
)

logger = logging.getLogger(__name__)


def _require_superuser(ws: Any) -> int | None:
    """Return the authenticated account_id if superuser, or None."""
    try:
        from airunner_services.api.ws_tenant import resolve_ws_tenant

        _tenant, account_id = resolve_ws_tenant(ws)
        if account_id is None:
            return None
        from extensions.auth.server.models import Account

        acct = Account.objects.get(account_id)
        if acct is None or not getattr(acct, "is_superuser", False):
            return None
        return account_id
    except Exception:
        return None


def _owned_conversation(conversation_id: int, account_id: int):
    """Return the caller's own conversation, or None."""
    from airunner_services.database.models.conversation import Conversation

    conv = Conversation.objects.get(conversation_id)
    if conv is None or conv.user_id != account_id:
        return None
    return conv


@_rpc_register("GET", "/api/v1/uwuchat/code-mode/{conversation_id}")
async def _rpc_code_mode_get(body: dict, **kw: Any) -> dict[str, Any]:
    """Return whether code mode is on for one of the admin's own
    conversations."""
    account_id = _require_superuser(kw.get("ws"))
    if account_id is None:
        return {"status": 403, "body": {"error": "Admin access required"}}
    pp: dict = kw.get("path_params", {})
    raw_id = pp.get("conversation_id", "")
    if not raw_id.isdigit():
        return {"status": 400, "body": {"error": "Invalid conversation_id"}}
    try:
        from projects.uwuchat.server.code_mode_service import (
            get_code_mode_slug,
            is_code_mode_enabled,
        )

        conv = _owned_conversation(int(raw_id), account_id)
        if conv is None:
            return {
                "status": 404,
                "body": {"error": "Conversation not found"},
            }
        return {
            "status": 200,
            "body": {
                "enabled": is_code_mode_enabled(conv),
                "mode": get_code_mode_slug(conv),
            },
        }
    except Exception as exc:
        return _rpc_error_response(
            exc, logger=logger, context="code-mode get failed",
        )


@_rpc_register("PUT", "/api/v1/uwuchat/code-mode/{conversation_id}")
async def _rpc_code_mode_set(body: dict, **kw: Any) -> dict[str, Any]:
    """Turn code mode on/off for one of the admin's own conversations."""
    account_id = _require_superuser(kw.get("ws"))
    if account_id is None:
        return {"status": 403, "body": {"error": "Admin access required"}}
    pp: dict = kw.get("path_params", {})
    raw_id = pp.get("conversation_id", "")
    if not raw_id.isdigit():
        return {"status": 400, "body": {"error": "Invalid conversation_id"}}
    try:
        from projects.uwuchat.server.code_mode_service import set_code_mode

        conversation_id = int(raw_id)
        if _owned_conversation(conversation_id, account_id) is None:
            return {
                "status": 404,
                "body": {"error": "Conversation not found"},
            }
        slug = body.get("mode")
        enabled, mode = set_code_mode(
            conversation_id, bool(body.get("enabled")), slug=slug,
        )
        return {"status": 200, "body": {"enabled": enabled, "mode": mode}}
    except ValueError as exc:
        return {"status": 400, "body": {"error": str(exc)}}
    except Exception as exc:
        return _rpc_error_response(
            exc, logger=logger, context="code-mode set failed",
        )
