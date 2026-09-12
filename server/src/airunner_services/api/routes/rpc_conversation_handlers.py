"""RPC handlers for conversation management."""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.api.routes.events import (
    _rpc_error_response,
    _rpc_register,
)

logger = logging.getLogger(__name__)


def _conv_auth(kw: dict) -> int | None:
    """Resolve and return the account_id from the WS context.

    Returns None when the socket is unauthenticated — callers must
    reject the request with a 401-equivalent response.
    """
    ws = kw.get("ws")
    if ws is None:
        return None
    from airunner_services.api.ws_tenant import resolve_ws_tenant

    _tenant, account_id = resolve_ws_tenant(ws)
    return account_id


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


def _conversation_manager():
    from airunner_services.conversations.conversation_history_manager import (
        ConversationHistoryManager,
    )
    return ConversationHistoryManager()


@_rpc_register("GET", "/api/v1/llm/conversations")
async def _rpc_conversations_list(body: dict, **kw: Any) -> dict[str, Any]:
    """List conversations."""
    if _conv_auth(kw) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    try:
        convs = _conversation_manager().list_conversations(
            limit=int(body.get("limit", 50))
        )
        return {"status": 200, "body": {"conversations": convs}}
    except Exception:
        return {"status": 200, "body": {"conversations": []}}


@_rpc_register("POST", "/api/v1/llm/conversations")
async def _rpc_conversations_create(body: dict, **kw: Any) -> dict[str, Any]:
    """Create a new conversation."""
    if _conv_auth(kw) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    try:
        session = _conversation_manager().create_conversation(
            max_messages=body.get("max_messages"),
        )
        return {"status": 200, "body": session}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="conversations create failed",
        )


@_rpc_register("DELETE", "/api/v1/llm/conversations/{conv_id}")
async def _rpc_conversations_delete(body: dict, **kw: Any) -> dict[str, Any]:
    """Delete a conversation."""
    if _conv_auth(kw) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    pp: dict = kw.get("path_params", {})
    raw_id = pp.get("conv_id", "")
    if not raw_id.isdigit():
        return {"status": 400, "body": {"error": "Invalid ID"}}
    try:
        _conversation_manager().delete_conversation(int(raw_id))
        return {"status": 200, "body": {"status": "deleted"}}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="conversations delete failed",
        )


@_rpc_register("GET", "/api/v1/llm/conversations/session")
async def _rpc_conversations_session(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Get a conversation session."""
    if _conv_auth(kw) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    try:
        conv_id = body.get("conversation_id")
        logger.debug(
            "[MOOD DEBUG] RPC session requested conv_id=%s", conv_id,
        )
        session = _conversation_manager().get_conversation_session(
            conversation_id=int(conv_id) if conv_id else None,
            max_messages=int(body.get("max_messages", 50)),
        )
        logger.debug(
            "[MOOD DEBUG] RPC session response current_mood=%r",
            session.get("current_mood"),
        )
        return {"status": 200, "body": session}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="conversations session failed",
        )


@_rpc_register("POST", "/api/v1/llm/conversations/select")
async def _rpc_conversations_select(body: dict, **kw: Any) -> dict[str, Any]:
    """Select a conversation."""
    if _conv_auth(kw) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    try:
        conv_id = body.get("conversation_id")
        if conv_id:
            session = _conversation_manager().get_conversation_session(
                conversation_id=int(conv_id),
            )
            return {"status": 200, "body": session}
        return {"status": 400, "body": {"error": "Missing conversation_id"}}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="conversations select failed",
        )


_SKIP_META = {"proactive_trigger", "tool_calls", "tool_result"}


@_rpc_register(
    "DELETE",
    "/api/v1/llm/chatbot/{chatbot_id}/messages/{visible_index}",
)
async def _rpc_message_delete(body: dict, **kw: Any) -> dict[str, Any]:
    """Truncate thread from visible_index onward (admin only).

    visible_index matches the client's filtered (user+assistant) array
    which spans multiple Conversation rows.  We walk all conversations
    for this chatbot in order, skipping tool/trigger entries, and cut
    at the first visible message that matches the requested index, then
    delete all later conversations.

    Superuser check: this operation modifies persistent conversation
    data.  Per the UwUchat architecture doc ("Messages are append-only
    — no edits, no deletes"), regular users must never call this route.
    """
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {
            "status": 403,
            "body": {"error": "Admin access required"},
        }

    from airunner_services.database.models.conversation import Conversation

    pp: dict = kw.get("path_params", {})
    raw_bot = pp.get("chatbot_id", "")
    raw_idx = pp.get("visible_index", "")
    if not raw_bot.isdigit() or not raw_idx.isdigit():
        return {
            "status": 400,
            "body": {"error": "Invalid chatbot_id or visible_index"},
        }
    chatbot_id = int(raw_bot)
    visible_target = int(raw_idx)

    try:
        conversations = (
            Conversation.objects.query()
            .filter(Conversation.chatbot_id == chatbot_id)
            .order_by(Conversation.id.asc())
            .all()
        )
        if not conversations:
            return {"status": 404, "body": {"error": "No conversations found"}}

        visible_count = 0
        cut_conv = None
        cut_db_idx = 0

        for conv in conversations:
            msgs = list(getattr(conv, "value", None) or [])
            for db_idx, msg in enumerate(msgs):
                if not isinstance(msg, dict):
                    continue
                if msg.get("metadata_type") in _SKIP_META:
                    continue
                if msg.get("role") not in ("user", "assistant"):
                    continue
                if visible_count == visible_target:
                    cut_conv = conv
                    cut_db_idx = db_idx
                    break
                visible_count += 1
            if cut_conv is not None:
                break

        if cut_conv is None:
            return {
                "status": 400,
                "body": {"error": "visible_index out of range"},
            }

        # Count visible messages BEFORE any mutations for the audit record.
        original_visible = 0
        for conv in conversations:
            for msg in (getattr(conv, "value", None) or []):
                if (
                    isinstance(msg, dict)
                    and msg.get("metadata_type") not in _SKIP_META
                    and msg.get("role") in ("user", "assistant")
                ):
                    original_visible += 1

        # Truncate the conversation that contains the cut point.
        cut_msgs = list(getattr(cut_conv, "value", None) or [])
        Conversation.objects.update(
            pk=cut_conv.id, value=cut_msgs[:cut_db_idx]
        )

        # Delete every conversation that comes after the cut one.
        for conv in conversations:
            if conv.id > cut_conv.id:
                Conversation.delete(pk=conv.id)
        try:
            from airunner_services.events.recorder import record

            record(
                "message_delete",
                chatbot_id=chatbot_id,
                actor="admin",
                payload={
                    "visible_index": visible_target,
                    "messages_removed": (
                        original_visible - visible_target
                    ),
                },
                conversation_id=cut_conv.id,
                sequence_num=visible_target,
            )
        except Exception:
            pass

        return {"status": 200, "body": {"kept": visible_target}}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="message delete failed",
        )


@_rpc_register("POST", "/api/v1/llm/conversations/truncate")
async def _rpc_conversations_truncate(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Truncate a conversation to keep messages[0:keep_count]."""
    if _conv_auth(kw) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    try:
        from airunner_services.database.models.conversation import Conversation

        conv_id = body.get("conversation_id")
        keep_count = int(body.get("keep_count", 0))
        if not conv_id or keep_count < 0:
            return {
                "status": 400,
                "body": {
                    "error": "conversation_id and keep_count are required"
                },
            }
        conversation = Conversation.objects.filter_by_first(id=int(conv_id))
        if conversation is None:
            return {
                "status": 404,
                "body": {"error": f"Conversation {conv_id} not found"},
            }
        raw = list(getattr(conversation, "value", None) or [])
        Conversation.objects.update(
            pk=int(conv_id), value=list(raw[:keep_count])
        )
        try:
            from airunner_services.events.recorder import record

            chatbot_id = getattr(conversation, "chatbot_id", None)
            if chatbot_id:
                record(
                    "conversation_truncate",
                    chatbot_id=chatbot_id,
                    actor="admin",
                    payload={
                        "keep_count": keep_count,
                        "original_count": len(raw),
                    },
                    conversation_id=int(conv_id),
                )
        except Exception:
            pass

        return {
            "status": 200,
            "body": {
                "truncated": True,
                "kept": keep_count,
                "original_count": len(raw),
            },
        }
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="conversations truncate failed",
        )


@_rpc_register("POST", "/api/v1/llm/conversations/previews")
async def _rpc_conversation_previews(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Return a truncated last-message preview per chatbot_id.

    Batched — one WS call for the whole roster instead of one
    round-trip per chatbot.  Returns only ``chatbot_id``, ``preview``
    (last message content truncated to 64 characters), and
    ``updated_at`` per bot.  Never exposes the full ``value``,
    ``summary``, ``user_data``, or any other Conversation columns.
    """
    if _conv_auth(kw) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    chatbot_ids = body.get("chatbot_ids", [])
    if not isinstance(chatbot_ids, list) or not chatbot_ids:
        return {"status": 200, "body": {"previews": {}}}
    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        previews: dict[str, dict[str, Any]] = {}
        for cid in chatbot_ids:
            try:
                cid = int(cid)
            except (TypeError, ValueError):
                continue
            row = (
                Conversation.objects.query()
                .filter(Conversation.chatbot_id == cid)
                .order_by(Conversation.updated_at.desc())
                .first()
            )
            preview: str | None = None
            updated_at: str | None = None
            if row is not None:
                updated_at = (
                    row.updated_at.isoformat()
                    if row.updated_at
                    else None
                )
                messages = row.value or []
                if isinstance(messages, list) and messages:
                    last = messages[-1]
                    if isinstance(last, dict):
                        content = last.get("content", "")
                        if isinstance(content, str) and content:
                            flat = content.replace("\n", " ").strip()
                            preview = (
                                flat[:64] + "\u2026"
                                if len(flat) > 64
                                else flat
                            )
            previews[str(cid)] = {
                "preview": preview,
                "updated_at": updated_at,
            }
        return {"status": 200, "body": {"previews": previews}}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="conversation previews failed",
        )
