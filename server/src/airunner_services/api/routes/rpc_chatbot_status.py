"""RPC handlers for chatbot online/offline status, blocking, and reporting."""

from __future__ import annotations

import logging
import time
from typing import Any

from airunner_services.api.routes.events import (
    _rpc_error_response,
    _rpc_register,
)

logger = logging.getLogger(__name__)


def _get_chatbot(chatbot_id: int):
    from airunner_services.database.models.chatbot import Chatbot
    return Chatbot.objects.get(chatbot_id)


def _status_payload(bot) -> dict:
    from datetime import datetime, timezone

    offline_until = getattr(bot, "offline_until", None)
    if offline_until and isinstance(offline_until, str):
        offline_until = datetime.fromisoformat(offline_until)
    if offline_until and offline_until.tzinfo is None:
        offline_until = offline_until.replace(tzinfo=timezone.utc)
    is_online = getattr(bot, "is_online", True)
    if not is_online and offline_until:
        if datetime.now(timezone.utc) >= offline_until:
            is_online = True
            offline_until = None
    return {
        "is_online": is_online,
        "offline_until": (
            offline_until.isoformat() if offline_until else None
        ),
        "has_blocked_user": getattr(bot, "has_blocked_user", False),
        "blocked_by_user": getattr(bot, "blocked_by_user", False),
    }


@_rpc_register(
    "GET", "/api/v1/chatbots/{chatbot_id}/status"
)
async def _rpc_chatbot_status(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Return online/block status for a chatbot."""
    try:
        pp = kw.get("path_params", {})
        chatbot_id = int(pp.get("chatbot_id", 0))
        bot = _get_chatbot(chatbot_id)
        if bot is None:
            return {"status": 404, "body": {"error": "Not found"}}
        return {"status": 200, "body": _status_payload(bot)}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="chatbot status error",
        )


@_rpc_register(
    "POST", "/api/v1/chatbots/{chatbot_id}/block"
)
async def _rpc_block_chatbot(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """User blocks a chatbot."""
    try:
        from airunner_services.database.models.chatbot import Chatbot

        pp = kw.get("path_params", {})
        chatbot_id = int(pp.get("chatbot_id", 0))
        bot = _get_chatbot(chatbot_id)
        if bot is None:
            return {"status": 404, "body": {"error": "Not found"}}
        Chatbot.objects.update(chatbot_id, blocked_by_user=True)
        return {"status": 200, "body": {"blocked_by_user": True}}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="block chatbot error",
        )


@_rpc_register(
    "DELETE", "/api/v1/chatbots/{chatbot_id}/block"
)
async def _rpc_unblock_chatbot(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """User unblocks a chatbot (also clears chatbot's block of user)."""
    try:
        from airunner_services.database.models.chatbot import Chatbot

        pp = kw.get("path_params", {})
        chatbot_id = int(pp.get("chatbot_id", 0))
        bot = _get_chatbot(chatbot_id)
        if bot is None:
            return {"status": 404, "body": {"error": "Not found"}}
        Chatbot.objects.update(
            chatbot_id,
            blocked_by_user=False,
            has_blocked_user=False,
        )
        return {
            "status": 200,
            "body": {
                "blocked_by_user": False,
                "has_blocked_user": False,
            },
        }
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="unblock chatbot error",
        )


@_rpc_register(
    "POST", "/api/v1/chatbots/{chatbot_id}/omnipotent-knowledge"
)
async def _rpc_toggle_omnipotent_knowledge(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Toggle omnipotent knowledge on/off for the system bot.

    Only the system bot (is_system_bot=True) supports this feature.
    """
    try:
        from airunner_services.database.models.chatbot import Chatbot

        pp = kw.get("path_params", {})
        chatbot_id = int(pp.get("chatbot_id", 0))
        bot = _get_chatbot(chatbot_id)
        if bot is None:
            return {"status": 404, "body": {"error": "Not found"}}
        if not getattr(bot, "is_system_bot", False):
            return {
                "status": 403,
                "body": {
                    "error": (
                        "Omnipotent knowledge is only available "
                        "for the system bot"
                    ),
                },
            }
        enabled = bool(body.get("enabled", False))
        Chatbot.objects.update(
            chatbot_id, omnipotent_knowledge=enabled,
        )
        return {
            "status": 200,
            "body": {"omnipotent_knowledge": enabled},
        }
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="omnipotent knowledge toggle error",
        )


_VALID_REPORT_REASONS = frozenset(
    {"Inappropriate", "Harmful/unsafe", "Off-character", "Other"}
)

# In-memory sliding-window rate limiter for the report endpoint.
# Keyed on account_id, stores a list of epoch timestamps for the
# last hour.  Pruned on every check.
_REPORT_RATE_WINDOW: dict[int, list[float]] = {}
_REPORT_MAX_PER_HOUR = 10
_REPORT_WINDOW_SECONDS = 3600


def _check_report_rate_limit(account_id: int) -> bool:
    """Return True if the account is still under the rate limit.

    Prunes expired entries and checks the count against the
    sliding window.  Mutates _REPORT_RATE_WINDOW in place.
    """
    now = time.time()
    cutoff = now - _REPORT_WINDOW_SECONDS
    timestamps = _REPORT_RATE_WINDOW.get(account_id, [])
    timestamps = [t for t in timestamps if t > cutoff]
    _REPORT_RATE_WINDOW[account_id] = timestamps
    if len(timestamps) >= _REPORT_MAX_PER_HOUR:
        return False
    timestamps.append(now)
    _REPORT_RATE_WINDOW[account_id] = timestamps
    return True


def _resolve_reporting_account_id(kw: dict) -> int | None:
    """Return the authenticated account ID for the RPC request."""
    ws = kw.get("ws")
    if ws is None:
        return None
    from airunner_services.api.ws_tenant import resolve_ws_tenant

    _tenant, account_id = resolve_ws_tenant(ws)
    return account_id


@_rpc_register(
    "POST", "/api/v1/chatbots/{chatbot_id}/report"
)
async def _rpc_report_chatbot_message(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """Report a chatbot message as abusive or inappropriate.

    Rate-limited to 10/hour per account via an in-memory
    sliding-window counter keyed on account_id.
    """
    account_id = _resolve_reporting_account_id(kw)
    if account_id is None:
        return {
            "status": 401,
            "body": {"error": "Authentication required"},
        }

    if not _check_report_rate_limit(account_id):
        return {
            "status": 429,
            "body": {"error": "Too many reports. Try again later."},
        }

    pp = kw.get("path_params", {})
    try:
        chatbot_id = int(pp.get("chatbot_id", 0))
    except (TypeError, ValueError):
        return {
            "status": 400,
            "body": {"error": "Invalid chatbot_id"},
        }

    reason = body.get("reason", "")
    if reason not in _VALID_REPORT_REASONS:
        return {
            "status": 400,
            "body": {
                "error": f"Invalid reason. Must be one of: "
                f"{', '.join(sorted(_VALID_REPORT_REASONS))}",
            },
        }

    detail = str(body.get("detail", "") or "")[:500]
    message_id = body.get("message_id")
    if message_id is not None:
        try:
            message_id = int(message_id)
        except (TypeError, ValueError):
            message_id = None

    payload: dict[str, Any] = {"reason": reason}
    if detail:
        payload["detail"] = detail
    if message_id is not None:
        payload["message_id"] = message_id

    try:
        from airunner_services.events.recorder import record

        from extensions.auth.server.models import Account

        username = f"account_{account_id}"
        try:
            acct = Account.objects.get(account_id)
            if acct and getattr(acct, "username", None):
                username = acct.username
        except Exception:
            pass

        record(
            event_type="user_reported",
            chatbot_id=chatbot_id,
            actor=username,
            actor_user_id=account_id,
            payload=payload,
        )
        return {"status": 200, "body": {"status": "received"}}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="report chatbot message error",
        )
