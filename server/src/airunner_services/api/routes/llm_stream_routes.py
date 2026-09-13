"""Websocket streaming routes for runtime-backed LLM endpoints."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from airunner_services.api.ws_rate_limiter import (
    check_llm_stream_rate,
)
from airunner_services.api.ws_tenant import (
    resolve_ws_tenant,
    ws_tenant_scope,
)
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

from .llm_runtime import (
    CODE_MODE_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    _conversation_is_code_mode,
    require_websocket_runtime_registry,
    resolve_llm_client,
    stream_runtime,
    websocket_envelope,
)
from .llm_runtime_rag import websocket_chunk

# Rate limiting is handled by the shared SlidingWindowRateLimiter
# in ws_rate_limiter.py (30 msg/min per account).  The old per-request
# cooldown (_MIN_REQUEST_INTERVAL) and _last_request_time dict have been
# replaced by the sliding-window counter.


async def _restore_stored_mood_on_connect(websocket) -> None:
    """Emit the persisted kaomoji on WS connect, before the first message.

    Determines the active chatbot from the conversation_id in the WS
    URL query string, then finds the most recent conversation for that
    chatbot that has a stored mood.  Decryption failures on individual
    rows (stale DEK after a container restart) are silently skipped —
    mood restoration is best-effort.
    """
    from airunner_services.utils.crypto.data_encryption import (
        DataEncryptionError,
    )

    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )
        qs = (websocket.scope.get("query_string") or b"").decode()
        params = parse_qs(qs)
        raw = params.get("conversation_id", [None])[0]
        chatbot_id = None
        if raw:
            try:
                ref_conv = Conversation.objects.get(int(raw))
                if ref_conv:
                    chatbot_id = getattr(ref_conv, "chatbot_id", None)
            except (ValueError, TypeError, DataEncryptionError):
                pass
        conv = None
        try:
            recent = (
                Conversation.objects.query()
                .order_by(Conversation.id.desc())
                .limit(20)
                .all()
            )
        except DataEncryptionError:
            logger.warning(
                "[MOOD DEBUG] Skipping mood restore — DEK cache stale "
                "(re-authenticate to re-populate)"
            )
            return
        if recent:
            for c in recent:
                if (
                    chatbot_id is not None
                    and getattr(c, "chatbot_id", None) != chatbot_id
                ):
                    continue
                try:
                    mood = (c.user_data or {}).get("current_mood")
                except DataEncryptionError:
                    continue
                if mood and mood.get("mood"):
                    conv = c
                    break
            if conv is None:
                try:
                    conv = recent[0]
                except (IndexError, DataEncryptionError):
                    return
        if not conv:
            return
        try:
            mood = (conv.user_data or {}).get("current_mood")
        except DataEncryptionError:
            return
        if not mood or not mood.get("mood"):
            return
        logger.debug(
            "[MOOD DEBUG] _restore_stored_mood_on_connect "
            "conv_id=%s chatbot_id=%s emitting mood=%r kaomoji=%r",
            conv.id, getattr(conv, "chatbot_id", None),
            mood.get("mood"), mood.get("kaomoji"),
        )
        await websocket.send_json({
            "type": "mood",
            "mood": mood.get("mood", "neutral"),
            "emoji": mood.get("emoji", "😐"),
            "kaomoji": mood.get("kaomoji", "(｡◕ᴗ◕｡)"),
            "done": False,
        })
    except DataEncryptionError:
        logger.warning(
            "[MOOD DEBUG] _restore_stored_mood_on_connect — "
            "DEK cache stale, skipping mood restore. "
            "Client should re-authenticate to re-populate the cache."
        )
    except Exception:
        logger.warning(
            "[MOOD DEBUG] _restore_stored_mood_on_connect FAILED",
            exc_info=True,
        )


async def _emit_stored_mood(data: dict[str, Any], websocket) -> None:
    """Emit the persisted mood from conv.user_data on first WS message
    or restore_mood request.

    The client sends conversation_id; we look up its chatbot and find
    the most recent conversation for that chatbot with a stored mood.
    """
    conv_id_raw = data.get("conversation_id")
    if not conv_id_raw:
        return
    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )
        conv_id = int(conv_id_raw)
        # Resolve the chatbot from the specified conversation
        ref = Conversation.objects.get(conv_id)
        chatbot_id = getattr(ref, "chatbot_id", None) if ref else None
        # Scan recent conversations for this chatbot with stored mood
        mood = None
        recent = (
            Conversation.objects.query()
            .order_by(Conversation.id.desc())
            .limit(20)
            .all()
        )
        if recent:
            for c in recent:
                if (
                    chatbot_id is not None
                    and getattr(c, "chatbot_id", None) != chatbot_id
                ):
                    continue
                found = (c.user_data or {}).get("current_mood")
                if found and found.get("mood"):
                    mood = found
                    break
        if not mood:
            return
        await websocket.send_json({
            "type": "mood",
            "mood": mood.get("mood", "neutral"),
            "emoji": mood.get("emoji", "😐"),
            "kaomoji": mood.get("kaomoji", "(｡◕ᴗ◕｡)"),
            "done": False,
        })
    except Exception:
        pass


router = APIRouter()
logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)


async def _stream_to_socket(client, websocket: WebSocket, envelope) -> None:
    """Stream all deltas for one request to the websocket."""
    async for delta in stream_runtime(client, envelope):
        payload = websocket_chunk(delta)
        await websocket.send_json(payload)
        if delta.final:
            break


@router.websocket("/stream")
async def websocket_chat(websocket: WebSocket):
    """Stream chat responses from the runtime-backed local LLM."""
    # Resolve tenant context *before* accepting so we can reject
    # unauthenticated connections with a clean close rather than
    # accepting a socket we will immediately close.
    tenant_key, account_id = resolve_ws_tenant(websocket)
    if account_id is None:
        await websocket.close(code=4001, reason="Authentication required")
        logger.warning("LLM stream WS rejected — missing or invalid token")
        return
    await websocket.accept()
    # Activate the caller's tenant for the life of the socket so generated
    # conversations are persisted to their schema rather than the anonymous
    # one. WS upgrades skip the HTTP auth middleware, so this must be done
    # here. See airunner_services.api.ws_tenant.
    with ws_tenant_scope(websocket) as (_tenant_key, account_id):
        qs = (websocket.scope.get("query_string") or b"").decode()
        params = parse_qs(qs)
        chatbot_id = params.get("chatbot_id", [None])[0]
        conversation_id = params.get("conversation_id", [None])[0]
        logger.info(
            "LLM stream WS connected account_id=%s "
            "chatbot_id=%s conversation_id=%s",
            account_id, chatbot_id, conversation_id,
        )
        try:
            client = resolve_llm_client(
                require_websocket_runtime_registry(websocket)
            )
            # Restore the stored kaomoji immediately on connect by
            # reading conversation_id from the WS query string and
            # emitting a mood event before the first user message.
            await _restore_stored_mood_on_connect(websocket)
            await _chat_loop(client, websocket, account_id)
        except WebSocketDisconnect:
            logger.info("WebSocket connection closed")
        except HTTPException as exc:
            await websocket.send_json(
                {"type": "error", "content": exc.detail, "done": True}
            )
        except Exception as exc:
            logger.error("WebSocket error: %s", exc, exc_info=True)
            await websocket.send_json(
                {
                    "type": "error",
                    "content": "We are experiencing an outage, please try again later.",
                    "done": True,
                }
            )


def _resolve_max_output_token_ceiling(account_id: int | None) -> int:
    """Return the self-hosted output token ceiling."""
    del account_id
    return DEFAULT_MAX_OUTPUT_TOKENS


def _try_load_quota_checker():
    """Return ``is_over_quota`` from the active project, or None."""
    try:
        import importlib
        import os

        project = os.environ.get("AIRUNNER_PROJECT", "")
        if not project:
            from airunner_services.conf import settings

            project = getattr(settings, "AIRUNNER_PROJECT", "") or ""
        if not project:
            return None
        mod = importlib.import_module(
            f"projects.{project}.server.quota_service"
        )
        return mod.is_over_quota
    except ImportError:
        return None


def _try_load_daily_token_checker():
    """Return ``is_over_daily_token_limit`` from the active project,
    or None."""
    try:
        import importlib
        import os

        project = os.environ.get("AIRUNNER_PROJECT", "")
        if not project:
            from airunner_services.conf import settings

            project = getattr(settings, "AIRUNNER_PROJECT", "") or ""
        if not project:
            return None
        mod = importlib.import_module(
            f"projects.{project}.server.quota_service"
        )
        return mod.is_over_daily_token_limit
    except ImportError:
        return None


def _ensure_session_rotation(data: dict) -> None:
    """Rotate the session and background-summarize any cold ones."""
    try:
        chatbot_id = data.get("chatbot_id")
        if not chatbot_id:
            return
        from airunner_services.llm.episodic_summarizer import (
            summarize_session,
        )
        from airunner_services.llm.session_manager import (
            SessionManager,
        )
        manager = SessionManager()
        manager.get_or_create_session(int(chatbot_id))
        for sid in manager.pending_cold_sessions(int(chatbot_id)):
            asyncio.create_task(summarize_session(sid, app=None))
    except Exception:
        pass

async def _chat_loop(
    client, websocket: WebSocket, account_id: int | None
) -> None:
    """Process chat messages until the socket closes."""
    from airunner_services.api.ws_tenant import ws_dek_scope
    from airunner_services.llm.safety.account_context import (
        set_current_account_id,
    )

    _mood_emitted = False
    # Lazy-load quota service (UwUchat project only).
    _is_over_quota = _try_load_quota_checker()
    # Lazy-load daily-token checker (UwUchat project only).
    _is_over_daily_token_limit = _try_load_daily_token_checker()
    # Resolve the per-tier max-output-token ceiling once per
    # connection — the tier cannot change mid-session.
    _max_token_ceiling = _resolve_max_output_token_ceiling(account_id)
    while True:
        data = await websocket.receive_json()
        with ws_dek_scope(account_id):
            set_current_account_id(account_id)
            logger.debug(
                "WS_MSG type=%s chatbot_id=%s conv_id=%s has_msg=%s",
                data.get("type"),
                data.get("chatbot_id"),
                data.get("conversation_id"),
                bool(data.get("message") or data.get("messages")),
            )

            # On the first message, emit the stored mood from the DB so the
            # client restores the kaomoji without needing the session RPC.
            if not _mood_emitted:
                _mood_emitted = True
                await _emit_stored_mood(data, websocket)

            # Handle restore_mood messages — client sends this when
            # switching chatbots, carrying the new conversation_id.
            if data.get("type") == "restore_mood":
                await _emit_stored_mood(data, websocket)
                continue

            # Handle cancel for any previously running stream
            # (belt-and-suspenders; the concurrent cancel below is the
            # primary mechanism).
            if data.get("type") == "cancel":
                continue

            has_content = bool(
                str(data.get("message", "")).strip()
            ) or bool(data.get("messages"))
            if not has_content:
                await websocket.send_json(
                    {"type": "error", "content": "No message provided"}
                )
                continue

            # Session rotation — check for cold-session gap and fire
            # background episodic summarisation when the user actually
            # sends a message (not on character click).
            _ensure_session_rotation(data)

            if (
                account_id is not None
                and _is_over_quota is not None
                and _is_over_quota(account_id, grace_pct=100.0)
            ):
                await websocket.send_json({
                    "type": "quota_exceeded",
                    "message": (
                        "You've reached your message limit for "
                        "this period."
                    ),
                    "done": True,
                })
                continue

            if (
                account_id is not None
                and _is_over_daily_token_limit is not None
                and _is_over_daily_token_limit(account_id)
            ):
                await websocket.send_json({
                    "type": "quota_exceeded",
                    "message": (
                        "You've reached your daily token limit."
                    ),
                    "done": True,
                })
                continue

            # Per-user rate limiting: sliding-window counter prevents
            # rapid-fire abuse even within quota.  The shared limiter
            # allows 30 msg/min per account, keyed on account_id (not
            # IP) so shared-NAT users are not penalised.
            if not check_llm_stream_rate(account_id):
                await websocket.send_json({
                    "type": "rate_limited",
                    "message": (
                        "Please wait a moment before sending "
                        "another message."
                    ),
                    "done": True,
                })
                continue

            # Code-mode conversations get the framework chat budget
            # (8192) instead of the companion-tier ceiling — the inline
            # agent tools (execute_command, read_file, ...) narrate real
            # work that can legitimately run past a 500-token reply.
            # Detected per message via conversation_id so the change is
            # live the moment code mode is toggled (no reconnect needed).
            ceiling = _max_token_ceiling
            try:
                conv_id = data.get("conversation_id")
                if (
                    conv_id is not None
                    and _conversation_is_code_mode(int(conv_id))
                ):
                    ceiling = CODE_MODE_MAX_OUTPUT_TOKENS
            except (TypeError, ValueError):
                pass

            # Create the stream task while the DEK is still in context.
            # asyncio.create_task captures ambient contextvars at
            # creation time — if this ran outside ws_dek_scope, the
            # _stream_to_socket task would see dek=None and silently
            # fall back to global-key encryption on every message.
            stream_task: asyncio.Task = asyncio.create_task(
                _stream_to_socket(
                    client,
                    websocket,
                    websocket_envelope(
                        data,
                        max_tokens_ceiling=ceiling,
                    ),
                )
            )

        # Race the stream against an incoming cancel message so the client
        # can abort mid-generation without waiting for the full response.
        cancel_task: asyncio.Task = asyncio.create_task(
            websocket.receive_json()
        )

        done, pending = await asyncio.wait(
            {stream_task, cancel_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if cancel_task in done and not cancel_task.cancelled():
            incoming = cancel_task.result()
            if incoming.get("type") == "cancel":
                stream_task.cancel()
                try:
                    await stream_task
                except (asyncio.CancelledError, Exception):
                    pass
                await websocket.send_json({"type": "done", "done": True})
            else:
                # Non-cancel message arrived during streaming — wait for
                # the current stream to finish, then process it next turn.
                for t in pending:
                    t.cancel()
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass
        else:
            # Stream completed before any cancel arrived.
            cancel_task.cancel()
            try:
                await cancel_task
            except (asyncio.CancelledError, Exception):
                pass
