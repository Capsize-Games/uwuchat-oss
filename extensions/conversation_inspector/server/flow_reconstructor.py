"""Reconstruct the complete conversation flow from persisted data.

Reads a Conversation's stored messages (including tool call metadata and
tool results), partitions them into turns, and builds an ordered sequence
of flow steps representing the full AI agent execution path.
"""

from __future__ import annotations

from typing import Any, List, Optional

from airunner_services.database.models.chatbot import Chatbot
from airunner_services.llm.core.tool_registry import ToolRegistry
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application.get_logger import get_logger

from extensions.conversation_inspector.server.prompt_reconstructor import (
    reconstruct_per_turn_context,
    reconstruct_system_prompt,
)

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

_METADATA_TOOL_CALLS = "tool_calls"
_METADATA_TOOL_RESULT = "tool_result"
_METADATA_RAG_INJECTION = "rag_injection"
_METADATA_SEMANTIC_BRIDGE = "semantic_bridge"
_METADATA_PROACTIVE_TRIGGER = "proactive_trigger"
_METADATA_PROACTIVE_RESPONSE = "proactive_response"
_USER_ROLE = "user"
_ASSISTANT_ROLES = {"assistant", "bot"}
_SYSTEM_ROLE = "system"


def _is_user_message(msg: dict) -> bool:
    return msg.get("role") == _USER_ROLE and msg.get("metadata_type") is None


def _is_assistant_message(msg: dict) -> bool:
    return (
        msg.get("role") in _ASSISTANT_ROLES
        and msg.get("metadata_type") is None
    )


def _is_turn_starter(msg: dict) -> bool:
    """Return True if this message begins a new turn."""
    return _is_user_message(msg) or (
        msg.get("metadata_type") == _METADATA_PROACTIVE_TRIGGER
    )


def _reconcile_extractor_entries(
    turns: List[List[dict]],
    cid_to_turn: dict[str, int],
) -> None:
    """Move metadata entries whose call_chain_id points to a different
    turn index to the correct turn bucket.

    Background pipelines (knowledge extractor) write tool_calls /
    tool_result entries into the conversation's message history from
    a daemon thread.  When the thread finishes *after* the user has
    sent their next message, those entries land in the wrong turn
    under insertion-order partitioning.  This function re-routes them
    by the call_chain_id that :class:`DatabaseChatMessageHistory`
    attached when the entry was persisted.
    """
    for src_idx in range(len(turns)):
        to_move: list[int] = []
        for j, msg in enumerate(turns[src_idx]):
            cid = msg.get("call_chain_id")
            if cid is None:
                continue
            mt = msg.get("metadata_type")
            if mt not in ("tool_calls", "tool_result"):
                continue
            tgt_idx = cid_to_turn.get(cid)
            if tgt_idx is not None and tgt_idx != src_idx:
                to_move.append(j)
        # Remove in reverse order so indices remain valid.
        moved: list[dict] = []
        for j in reversed(to_move):
            moved.append(turns[src_idx].pop(j))
        for msg in reversed(moved):
            tgt_idx = cid_to_turn[msg["call_chain_id"]]
            turns[tgt_idx].append(msg)


def _partition_turns(messages: List[dict]) -> List[List[dict]]:
    """Partition a flat message list into turns.

    Each turn starts with a user message (or proactive trigger) and
    includes all subsequent messages until the next turn starter.
    """
    turns: List[List[dict]] = []
    current: List[dict] = []

    for msg in messages:
        if _is_turn_starter(msg):
            if current:
                turns.append(current)
            current = [msg]
        else:
            if current:
                current.append(msg)

    if current:
        turns.append(current)

    return turns


def _extract_turn_model(turn_messages: List[dict]) -> Optional[str]:
    """Return the model version from any rag_injection entry in this turn."""
    for msg in turn_messages:
        if msg.get("metadata_type") == _METADATA_RAG_INJECTION:
            model = msg.get("model_version")
            if model:
                return str(model)
    return None


def _token_estimate(char_count: int) -> int:
    """Rough token estimate from character count (~4 chars per token)."""
    return max(1, char_count // 4)


def _build_flow_steps(
    turn_messages: List[dict],
    system_prompt_data: Optional[dict] = None,
    per_turn_context_data: Optional[dict] = None,
    turn_model: Optional[str] = None,
) -> List[dict]:
    """Build ordered flow steps from one turn's messages.

    Args:
        turn_messages: All messages belonging to one turn (including metadata).
        system_prompt_data: Reconstructed system prompt to prepend as first step.
        per_turn_context_data: Dynamic context injected into the human turn.
        turn_model: Model version inferred from rag_injection metadata.

    Returns:
        List of flow step dicts with keys: type, label, content, metadata.
    """
    steps: List[dict] = []

    # Pre-compute prompt context so thinking/response steps can carry
    # the full prompt that was fed to the model for this call.
    _prompt_context_meta: dict[str, Any] = {}
    if system_prompt_data:
        sp_full = system_prompt_data.get("full_text", "")
        _prompt_context_meta["system_prompt_full_text"] = sp_full
        _prompt_context_meta["system_prompt_char_count"] = len(sp_full)
    if per_turn_context_data:
        ptc_full = per_turn_context_data.get("full_text", "")
        _prompt_context_meta["per_turn_context_full_text"] = ptc_full
        _prompt_context_meta["per_turn_context_char_count"] = len(ptc_full)

    # Stable system prompt — cache-preserved, shown first.
    if system_prompt_data:
        sp_full = system_prompt_data.get("full_text", "")
        steps.append(
            {
                "type": "system_prompt",
                "label": "System Prompt (cache-stable)",
                "content": (
                    sp_full[:120] + "…" if len(sp_full) > 120 else sp_full
                ),
                "metadata": {
                    "parts": system_prompt_data.get("parts", {}),
                    "full_text": sp_full,
                    "char_count": len(sp_full),
                    "token_estimate": _token_estimate(len(sp_full)),
                    "is_cache_stable": system_prompt_data.get(
                        "is_cache_stable", True
                    ),
                    "includes_mood": False,
                    "includes_datetime": False,
                },
            }
        )

    # Per-turn context injected into the human message — shown after system prompt.
    if per_turn_context_data:
        ptc_full = per_turn_context_data.get("full_text", "")
        ptc_parts = per_turn_context_data.get("parts", {})
        ptc_preview_parts = []
        if per_turn_context_data.get("has_datetime"):
            ptc_preview_parts.append("📅 datetime")
        if per_turn_context_data.get("has_mood"):
            ptc_preview_parts.append("🎭 mood")
        ptc_preview_parts.append("🛡 preflight")
        ptc_label = "Per-Turn Context → human turn"
        steps.append(
            {
                "type": "per_turn_context",
                "label": ptc_label,
                "content": " · ".join(ptc_preview_parts),
                "metadata": {
                    "parts": ptc_parts,
                    "full_text": ptc_full,
                    "char_count": len(ptc_full),
                    "token_estimate": _token_estimate(len(ptc_full)),
                    "has_datetime": per_turn_context_data.get(
                        "has_datetime", False
                    ),
                    "has_mood": per_turn_context_data.get("has_mood", False),
                    "has_preflight_dynamic": per_turn_context_data.get(
                        "has_preflight_dynamic", True
                    ),
                    "injection_target": per_turn_context_data.get(
                        "injection_target", "human_turn"
                    ),
                    "note": per_turn_context_data.get("note", ""),
                },
            }
        )

    for msg in turn_messages:
        role = msg.get("role", "unknown")
        msg_type = msg.get("metadata_type")
        timestamp = msg.get("timestamp", "")

        # ── RAG injection (inline, replaces bottom section) ─────────────
        if msg_type == _METADATA_RAG_INJECTION:
            is_active = msg.get("is_rag_active", False)
            doc_names = msg.get("active_document_names", []) or []
            doc_ids = msg.get("active_document_ids", []) or []
            preview = msg.get("rag_text_preview", "") or ""
            model_ver = msg.get("model_version", "") or ""
            preview_char_count = len(preview)

            if is_active or doc_names:
                label_docs = ", ".join(doc_names[:2])
                if len(doc_names) > 2:
                    label_docs += f" +{len(doc_names) - 2}"
                steps.append(
                    {
                        "type": "rag_step",
                        "label": (
                            f"RAG: {label_docs}"
                            if label_docs
                            else "RAG Context"
                        ),
                        "content": (
                            preview[:160]
                            if preview
                            else (
                                f"{len(doc_names)} document(s): "
                                f"{', '.join(doc_names)}"
                                if doc_names
                                else "RAG active"
                            )
                        ),
                        "metadata": {
                            "timestamp": timestamp,
                            "is_rag_active": is_active,
                            "doc_names": doc_names,
                            "doc_ids": doc_ids,
                            "rag_text_preview": preview,
                            "model_version": model_ver,
                            "char_count": preview_char_count,
                            "token_estimate": _token_estimate(
                                preview_char_count
                            ),
                        },
                    }
                )

        # ── Tool call request ────────────────────────────────────────────
        elif msg_type == _METADATA_TOOL_CALLS:
            tool_calls = msg.get("tool_calls", [])
            thinking = msg.get("thinking_content")

            if thinking and not any(
                s.get("type") == "thinking" for s in steps
            ):
                thinking_char_count = len(thinking)
                steps.append(
                    {
                        "type": "thinking",
                        "label": "Thinking",
                        "content": thinking,
                        "metadata": {
                            "timestamp": timestamp,
                            "model": turn_model,
                            "char_count": thinking_char_count,
                            "token_estimate": _token_estimate(
                                thinking_char_count
                            ),
                            **_prompt_context_meta,
                        },
                    }
                )

            for tc in tool_calls:
                tool_name = tc.get("name", "unknown")
                tool_args = tc.get("args", {})
                is_mood = tool_name == "update_mood"

                args_text = str(tool_args)
                steps.append(
                    {
                        "type": "mood_update" if is_mood else "tool_call",
                        "label": (
                            f"Mood → {tool_args.get('mood', '?')} "
                            f"{tool_args.get('emoji', '')}"
                            if is_mood
                            else f"Tool: {tool_name}"
                        ),
                        "content": (
                            f"Mood: {tool_args.get('mood', '?')} "
                            f"{tool_args.get('emoji', '')} — "
                            f"{tool_args.get('reason', '')}"
                            if is_mood
                            else (
                                f"Calls {tool_name} with args: "
                                f"{_format_args(tool_args)}"
                            )
                        ),
                        "metadata": {
                            "timestamp": timestamp,
                            "tool_name": tool_name,
                            "tool_category": _tool_category(tool_name),
                            "arguments": tool_args,
                            "tool_call_id": tc.get("id"),
                            "model": turn_model,
                            "char_count": len(args_text),
                            "token_estimate": _token_estimate(
                                len(args_text)
                            ),
                        },
                    }
                )

        # ── Tool result ──────────────────────────────────────────────────
        elif msg_type == _METADATA_TOOL_RESULT:
            tool_call_id = msg.get("tool_call_id", "unknown")
            result_content = msg.get("content", "")
            result_char_count = len(result_content)
            steps.append(
                {
                    "type": "tool_result",
                    "label": "Tool Result",
                    "content": _truncate_content(result_content, 500),
                    "metadata": {
                        "timestamp": timestamp,
                        "model": turn_model,
                        "full_content": result_content,
                        "tool_call_id": tool_call_id,
                        "char_count": result_char_count,
                        "token_estimate": _token_estimate(result_char_count),
                    },
                }
            )

        # ── Semantic bridge (pgvector-retrieved past exchanges) ───────────
        elif msg_type == _METADATA_SEMANTIC_BRIDGE:
            exchanges = msg.get("exchanges", []) or []
            preview_parts: list[str] = []
            for ex in exchanges:
                text = str(ex)[:120]
                if len(str(ex)) > 120:
                    text += "…"
                preview_parts.append(text)
            preview = "\n".join(preview_parts[:6])
            steps.append(
                {
                    "type": "semantic_bridge",
                    "label": f"Semantic Bridge ({len(exchanges)} exchange(s))",
                    "content": preview,
                    "metadata": {
                        "timestamp": timestamp,
                        "exchanges": exchanges,
                        "user_message": msg.get("user_message", ""),
                        "char_count": len(preview),
                        "token_estimate": _token_estimate(len(preview)),
                        "note": (
                            "Past exchanges retrieved via pgvector "
                            "semantic search and injected into the "
                            "per-turn context."
                        ),
                    },
                }
            )

        # ── Proactive trigger (hidden from user) ─────────────────────────
        elif msg_type == _METADATA_PROACTIVE_TRIGGER:
            content = msg.get("content", "")
            char_count = len(content)
            steps.append(
                {
                    "type": "proactive_trigger",
                    "label": "Proactive Trigger (hidden from user)",
                    "content": content,
                    "metadata": {
                        "timestamp": timestamp,
                        "char_count": char_count,
                        "token_estimate": _token_estimate(char_count),
                        "note": (
                            "Hidden user-role message that maintains "
                            "LLM turn order without being shown to the "
                            "user."
                        ),
                    },
                }
            )

        # ── Proactive response (bot-initiated message) ────────────────────
        elif msg_type == _METADATA_PROACTIVE_RESPONSE:
            content = msg.get("content", "")
            char_count = len(content)
            steps.append(
                {
                    "type": "response",
                    "label": (
                        f"Assistant: {msg.get('name', 'Bot')}"
                        " [proactive]"
                    ),
                    "content": content,
                    "metadata": {
                        "timestamp": timestamp,
                        "char_count": char_count,
                        "token_estimate": _token_estimate(char_count),
                        "model": turn_model,
                        "is_proactive": True,
                    },
                }
            )

        # ── Available tools metadata (debug info, not user-visible) ───
        elif msg_type == "available_tools":
            tool_names = msg.get("available_tools", [])
            content = msg.get("content", "")
            char_count = len(content)
            steps.append(
                {
                    "type": "system_message",
                    "label": "Available Tools",
                    "content": content,
                    "metadata": {
                        "timestamp": timestamp,
                        "char_count": char_count,
                        "tool_names": tool_names,
                    },
                }
            )

        # ── Regular messages (no metadata_type) ──────────────────────────
        elif msg_type is None:
            content = msg.get("content", "")
            thinking = msg.get("thinking_content")

            if role == _USER_ROLE:
                char_count = len(content)
                metadata: dict[str, Any] = {"timestamp": timestamp}
                if msg.get("model"):
                    metadata["model"] = msg.get("model")
                active_docs = msg.get("active_documents")
                if active_docs:
                    metadata["active_documents"] = list(active_docs)
                metadata["char_count"] = char_count
                metadata["token_estimate"] = _token_estimate(char_count)
                steps.append(
                    {
                        "type": "user_message",
                        "label": f"User: {msg.get('name', 'User')}",
                        "content": content,
                        "metadata": metadata,
                    }
                )

            elif role in _ASSISTANT_ROLES:
                if thinking and not any(
                    s.get("type") == "thinking" for s in steps
                ):
                    thinking_char_count = len(thinking)
                    steps.append(
                        {
                            "type": "thinking",
                            "label": "Thinking",
                            "content": thinking,
                            "metadata": {
                                "timestamp": timestamp,
                                "char_count": thinking_char_count,
                                "token_estimate": _token_estimate(
                                    thinking_char_count
                                ),
                                **_prompt_context_meta,
                            },
                        }
                    )
                char_count = len(content)
                steps.append(
                    {
                        "type": "response",
                        "label": f"Assistant: {msg.get('name', 'Assistant')}",
                        "content": content,
                        "metadata": {
                            "timestamp": timestamp,
                            "char_count": char_count,
                            "token_estimate": _token_estimate(char_count),
                            "model": turn_model,
                            **_prompt_context_meta,
                        },
                    }
                )

            elif role == _SYSTEM_ROLE:
                if "attached to this conversation" in content:
                    char_count = len(content)
                    steps.append(
                        {
                            "type": "rag_step",
                            "label": "RAG Context (system)",
                            "content": content,
                            "metadata": {
                                "timestamp": timestamp,
                                "char_count": char_count,
                                "token_estimate": _token_estimate(
                                    char_count
                                ),
                            },
                        }
                    )
                else:
                    char_count = len(content)
                    steps.append(
                        {
                            "type": "system_message",
                            "label": "System",
                            "content": content,
                            "metadata": {
                                "timestamp": timestamp,
                                "char_count": char_count,
                                "token_estimate": _token_estimate(
                                    char_count
                                ),
                            },
                        }
                    )

    return steps


def _format_args(args: Any) -> str:
    """Format tool arguments for compact display."""
    if not args:
        return "{}"
    try:
        formatted = {}
        for key, value in (args if isinstance(args, dict) else {}).items():
            val_str = str(value)
            if len(val_str) > 80:
                val_str = val_str[:77] + "..."
            formatted[key] = val_str
        return str(formatted)
    except Exception:
        return str(args)[:120]


_KNOWLEDGE_EXTRACTOR_TOOLS = frozenset(
    {"save_fact", "check_similar_facts", "retract_fact"}
)


def _tool_category(tool_name: str) -> str:
    """Return the ToolCategory value string for *tool_name*, or ''.

    Falls back to a known list for the knowledge extractor's tools,
    which are built as per-request closures and never registered in
    ToolRegistry.
    """
    info = ToolRegistry.get(tool_name)
    if info is not None:
        return info.category.value if hasattr(info.category, "value") else ""
    if tool_name in _KNOWLEDGE_EXTRACTOR_TOOLS:
        return "knowledge"
    return ""


def _truncate_content(content: str, max_chars: int) -> str:
    """Truncate one content string to max_chars with ellipsis."""
    if len(content) <= max_chars:
        return content
    return content[: max_chars - 3] + "..."


def get_chatbot_for_conversation(conversation: Any) -> Optional[Any]:
    """Load the Chatbot associated with one conversation."""
    if not conversation.chatbot_id:
        return None
    return (
        Chatbot.objects.query()
        .filter(Chatbot.id == conversation.chatbot_id)
        .first()
    )


def _extract_rag_metadata(messages: List[dict]) -> dict[str, Any]:
    """Extract RAG injection metadata entries for the per-turn badge."""
    rag_entries: List[dict] = []
    model_from_rag: Optional[str] = None

    for msg in messages:
        if msg.get("metadata_type") == _METADATA_RAG_INJECTION:
            rag_entries.append(msg)
            if not model_from_rag:
                model_from_rag = msg.get("model_version")

    turns_rag: dict[int, dict[str, Any]] = {}
    for idx, entry in enumerate(rag_entries):
        turns_rag[idx] = {
            "is_rag_active": entry.get("is_rag_active", False),
            "active_document_ids": entry.get("active_document_ids", []),
            "active_document_names": entry.get("active_document_names", []),
            "rag_text_preview": entry.get("rag_text_preview", ""),
            "is_reconstructed": False,
        }

    return {
        "model_version": model_from_rag,
        "turns": turns_rag,
        "entries": rag_entries,
    }


def _build_rag_context_for_turn(
    user_content: str,
    turn_index: int,
    extracted: dict[str, Any],
    turn_messages: List[dict],
) -> dict[str, Any]:
    """Build RAG context dict for one turn (used for turn-label badge only)."""
    # Prefer rag_injection entries found directly in turn_messages
    for msg in turn_messages:
        if msg.get("metadata_type") == _METADATA_RAG_INJECTION:
            doc_names = msg.get("active_document_names", []) or []
            doc_ids = msg.get("active_document_ids", []) or []
            preview = msg.get("rag_text_preview", "")
            is_active = msg.get("is_rag_active", False)
            documents = []
            for j, name in enumerate(doc_names):
                doc_entry: dict[str, Any] = {
                    "source": name,
                    "content": preview[:120] if j == 0 else "",
                    "score": None,
                }
                if j < len(doc_ids):
                    doc_entry["id"] = doc_ids[j]
                documents.append(doc_entry)
            return {
                "is_rag_active": is_active,
                "is_reconstructed": False,
                "documents": documents,
                "doc_names": doc_names,
                "rag_text_preview": preview,
            }

    # Fall back to indexed extraction
    turns_rag: dict = extracted.get("turns", {})
    if turn_index in turns_rag:
        stored = dict(turns_rag[turn_index])
        doc_names = stored.get("active_document_names", [])
        doc_ids = stored.get("active_document_ids", [])
        documents = []
        for j, name in enumerate(doc_names):
            doc_entry = {
                "source": name,
                "content": (
                    stored.get("rag_text_preview", "")[:120] if j == 0 else ""
                ),
                "score": None,
            }
            if j < len(doc_ids):
                doc_entry["id"] = doc_ids[j]
            documents.append(doc_entry)
        return {
            "is_rag_active": stored.get("is_rag_active", False),
            "is_reconstructed": False,
            "documents": documents,
            "doc_names": doc_names,
            "rag_text_preview": stored.get("rag_text_preview", ""),
        }

    if not user_content:
        return {"is_rag_active": False, "is_reconstructed": True, "documents": []}
    return {**_reconstruct_rag_context(user_content), "is_reconstructed": True}


def reconstruct_flow(conversation: Any) -> dict:
    """Reconstruct the complete flow for one conversation."""
    messages: List[dict] = (
        conversation.value if isinstance(conversation.value, list) else []
    )

    if not messages:
        return {
            "conversation_id": conversation.id,
            "title": conversation.title,
            "user_name": conversation.user_name or "Unknown",
            "chatbot": _build_chatbot_info(conversation),
            "turns": [],
            "total_tokens": 0,
            "total_characters": 0,
        }

    # Extract RAG metadata for badges (reads the full list, keeps all msgs)
    extracted_rag = _extract_rag_metadata(messages)

    # Partition into turns — all message types pass through (metadata
    # included).  Background-extractor messages may land in the wrong
    # turn because they arrive asynchronously.  Reconcile them below.
    raw_turns = _partition_turns(messages)

    # Build a {call_chain_id: turn_index} map by scanning each turn
    # bucket for its assistant message — those are tagged with
    # call_chain_id at persistence time (DatabaseChatMessageHistory
    # line ~533).  This is synchronous and works for live, in-progress
    # conversations (unlike ConversationTurn, which is only populated
    # at session close).
    cid_to_turn: dict[str, int] = {}
    for idx, turn_msgs in enumerate(raw_turns):
        for msg in turn_msgs:
            if _is_assistant_message(msg) and msg.get("call_chain_id"):
                cid_to_turn[msg["call_chain_id"]] = idx
                break

    # Move any metadata entry whose call_chain_id maps to a different
    # turn index to that turn's bucket.  This fixes the case where the
    # knowledge extractor's background thread finishes after the user
    # has already sent their next message.
    if cid_to_turn and len(raw_turns) > 1:
        _reconcile_extractor_entries(raw_turns, cid_to_turn)

    chatbot_info = _build_chatbot_info(
        conversation,
        model_from_rag=extracted_rag.get("model_version"),
    )

    user_data = conversation.user_data or {}
    current_mood = user_data.get("current_mood")
    chatbot = get_chatbot_for_conversation(conversation)

    system_prompt_data = reconstruct_system_prompt(
        chatbot=chatbot,
        current_mood=current_mood.get("mood") if current_mood else None,
        current_emoji=current_mood.get("emoji") if current_mood else None,
    )

    turns: List[dict] = []
    conversation_total_tokens = 0
    conversation_total_chars = 0
    for i, turn_msgs in enumerate(raw_turns):
        is_proactive = (
            bool(turn_msgs)
            and turn_msgs[0].get("metadata_type")
            == _METADATA_PROACTIVE_TRIGGER
        )
        first_msg = turn_msgs[0] if turn_msgs else None
        user_msg = (
            first_msg
            if first_msg and _is_user_message(first_msg)
            else None
        )
        display_msg = first_msg if is_proactive else user_msg
        user_content = user_msg.get("content", "") if user_msg else ""
        user_ts = (
            display_msg.get("timestamp") if display_msg else None
        )

        # Per-turn model inferred from rag_injection in this turn
        turn_model = _extract_turn_model(turn_msgs)

        # RAG context for the turn-label badge
        rag_context = _build_rag_context_for_turn(
            user_content, i, extracted_rag, turn_msgs,
        )

        # Per-turn context is not injected for proactive turns
        per_turn_context_data = (
            None
            if is_proactive
            else reconstruct_per_turn_context(
                chatbot=chatbot,
                current_mood=(
                    current_mood.get("mood") if current_mood else None
                ),
                current_emoji=(
                    current_mood.get("emoji") if current_mood else None
                ),
                user_message_timestamp=user_ts,
            )
        )

        # Build inline flow steps (system prompt prepended, all metadata)
        flow_steps = _build_flow_steps(
            turn_msgs,
            system_prompt_data=system_prompt_data,
            per_turn_context_data=per_turn_context_data,
            turn_model=turn_model,
        )

        # Compute totals for this turn from flow step metadata
        turn_total_tokens = sum(
            step.get("metadata", {}).get("token_estimate", 0)
            for step in flow_steps
        )
        turn_total_chars = sum(
            step.get("metadata", {}).get("char_count", 0)
            for step in flow_steps
        )
        conversation_total_tokens += turn_total_tokens
        conversation_total_chars += turn_total_chars

        turns.append(
            {
                "turn_index": i,
                "is_proactive": is_proactive,
                "user_message": (
                    {
                        "content": display_msg.get("content", ""),
                        "name": display_msg.get("name", "User"),
                        "timestamp": display_msg.get("timestamp", ""),
                        "is_proactive": is_proactive,
                    }
                    if display_msg
                    else None
                ),
                "system_prompt": system_prompt_data,
                "rag_context": rag_context,
                "flow_steps": flow_steps,
                "model": turn_model,
                "total_tokens": turn_total_tokens,
                "total_characters": turn_total_chars,
            }
        )

    return {
        "conversation_id": conversation.id,
        "title": conversation.title,
        "user_name": conversation.user_name or "Unknown",
        "chatbot": chatbot_info,
        "turns": turns,
        "total_tokens": conversation_total_tokens,
        "total_characters": conversation_total_chars,
    }


def _build_chatbot_info(
    conversation: Any,
    model_from_rag: Optional[str] = None,
) -> Optional[dict]:
    """Build chatbot info dict for display in the inspector UI."""
    chatbot = get_chatbot_for_conversation(conversation)
    effective_model = model_from_rag or (
        chatbot.model_version if chatbot else None
    ) or "unknown"

    if not chatbot:
        return {
            "name": conversation.chatbot_name or "Unknown",
            "botname": "Unknown",
            "model_version": effective_model,
            "model_type": "unknown",
        }

    return {
        "id": chatbot.id,
        "name": chatbot.name,
        "botname": chatbot.botname,
        "use_personality": chatbot.use_personality,
        "use_mood": chatbot.use_mood,
        "use_guardrails": chatbot.use_guardrails,
        "use_system_instructions": chatbot.use_system_instructions,
        "use_datetime": chatbot.use_datetime,
        "personality": (
            chatbot.bot_personality if chatbot.use_personality else None
        ),
        "guardrails_prompt": (
            chatbot.guardrails_prompt if chatbot.use_guardrails else None
        ),
        "system_instructions": (
            chatbot.system_instructions
            if chatbot.use_system_instructions
            else None
        ),
        "model_version": effective_model,
        "model_type": chatbot.model_type,
    }


def _reconstruct_rag_context(user_query: str) -> dict:
    """Reconstruct the RAG context post-hoc via TF-IDF (fallback)."""
    if not user_query:
        return {"query": "", "documents": []}

    try:
        from airunner_services.knowledge import get_knowledge_base

        kb = get_knowledge_base()
        results = kb.search_tfidf(user_query, max_results=5)
        documents = []
        for result in results:
            documents.append(
                {
                    "content": result.get("line", ""),
                    "source": result.get("file", "knowledge"),
                    "score": round(result.get("score", 0), 4),
                    "context": result.get("context", ""),
                }
            )
        return {"query": user_query, "documents": documents}
    except Exception as exc:
        logger.debug("Could not reconstruct RAG context: %s", exc)
        return {"query": user_query, "documents": []}
