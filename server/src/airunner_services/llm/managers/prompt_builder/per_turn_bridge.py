"""Per-turn session bridge — active concern, voice, and story events.

Provides continuity across sessions by injecting the chatbot's current
preoccupation, a voice sample from the last session, and any unsurfaced
story events that occurred while the user was away.

Also injects two cross-session retrieval signals (tail context and
semantic similarity search) via per_turn_bridge_retrieval.py.
"""

from __future__ import annotations

import logging
from typing import Optional

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.prompt_builder import (
    per_turn_bridge_retrieval,
    per_turn_bridge_semantic,
)
from airunner_services.llm.managers.prompt_builder.prompt_builder import (
    CONVERSATIONAL_ACTIONS,
)

logger = logging.getLogger(__name__)

_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "i", "you", "he", "she",
    "it", "we", "they", "me", "him", "her", "us", "them", "my", "your",
    "his", "its", "our", "their", "that", "this", "these", "those",
    "what", "who", "which", "when", "where", "why", "how", "and", "or",
    "but", "if", "in", "on", "at", "to", "for", "of", "with", "by",
    "from", "about", "into", "through", "not", "no", "so", "as", "up",
    "out", "then", "than",
})


def _content_words(text: str) -> set[str]:
    """Return lowercase alpha content words, filtering stopwords."""
    return {
        w for w in text.lower().split()
        if w.isalpha() and w not in _STOPWORDS and len(w) > 2
    }


def _shares_vocabulary(user_message: str, candidate: str) -> bool:
    """Return True when the two texts share at least one content word.

    Used to gate whether stale bridged content is shown to the system
    bot at all — rather than showing clearly unrelated prior-session
    content and relying on prompt instructions to keep it from
    surfacing, which proved unreliable in practice.
    """
    user_words = _content_words(user_message)
    if not user_words:
        return True
    candidate_words = _content_words(candidate)
    if not candidate_words:
        return True
    return bool(user_words & candidate_words)

_PRIOR_TAIL_HEADER_SYSTEM = (
    "[Background — topics from a previous, separate session. This is"
    " closed history, not an open task: nothing here is waiting to be"
    " finished, followed up on, or resolved, even if it looks"
    " incomplete. It has no bearing on what to say next. Answer only"
    " the user's current message, on its own terms, as the complete"
    " and only thing being asked right now.]"
)

_PRIOR_TAIL_HEADER_ROLEPLAY = (
    "[Background — topics from a previous session."
    " Use this as silent context only."
    " Do not reference it or acknowledge it.]"
)

_SEMANTIC_HEADER_SYSTEM = (
    "[Past exchanges from earlier sessions — closed history, not an"
    " open task. Nothing here is waiting to be finished or followed"
    " up on. Answer only the user's current message, on its own"
    " terms.]"
)

_SEMANTIC_HEADER_ROLEPLAY = (
    "[Past exchanges — background only."
    " React to the current message, not to this.]"
)


def bridge_part(owner, action: LLMActionType) -> Optional[str]:
    """Return session bridge context: concern, voice, events,
    plus cross-session tail and semantic retrieval.
    """
    if action not in CONVERSATIONAL_ACTIONS:
        return None
    chatbot = getattr(owner, "chatbot", None)
    chatbot_id = getattr(chatbot, "id", None) if chatbot else None
    if not chatbot_id:
        return None

    chatbot_name = getattr(chatbot, "name", "UwU")
    current_session_id = (
        per_turn_bridge_retrieval.get_current_session_id(owner)
    )
    wm = getattr(owner, "_workflow_manager", None)
    current_conv_id = (
        getattr(owner, "_conversation_id", None)
        or (getattr(wm, "_conversation_id", None) if wm else None)
    )

    user_message = (
        per_turn_bridge_retrieval.get_latest_user_message(owner)
    )

    # Part 1: Prior-session tail context (last exchanges).
    prior_tail_parts: list[str] = []
    per_turn_bridge_retrieval.append_prior_tail(
        prior_tail_parts,
        chatbot_id,
        current_session_id or 0,
        chatbot_name,
        current_conv_id,
        user_message or "",
    )

    # Part 2: Semantic retrieval (most relevant past exchanges).
    semantic_parts: list[str] = []
    if user_message and current_session_id is not None:
        per_turn_bridge_semantic.append_semantic_context(
            semantic_parts,
            chatbot_id,
            current_session_id,
            user_message,
            chatbot_name,
            owner,
        )

    # Per-turn always-on state (no session-start header).
    state_parts: list[str] = []
    _append_concern(state_parts, chatbot)
    _append_voice_sample(state_parts, chatbot)
    _append_inventory(state_parts, chatbot)

    # One-shot story events — only appear once, then marked surfaced.
    event_parts: list[str] = []
    _append_unsurfaced_events(event_parts, chatbot_id)

    # Store semantic bridge results so the conversation inspector can
    # display them as a separate flow step.  Best-effort — failures
    # must never block the conversation.
    _store_bridge_metadata(
        current_conv_id,
        prior_tail_parts,
        semantic_parts,
        user_message or "",
        chatbot_name,
    )

    is_system_bot = bool(getattr(chatbot, "is_system_bot", False))
    if is_system_bot and user_message:
        if prior_tail_parts and not _shares_vocabulary(
            user_message, " ".join(prior_tail_parts)
        ):
            prior_tail_parts = []
        if semantic_parts and not _shares_vocabulary(
            user_message, " ".join(semantic_parts)
        ):
            semantic_parts = []

    blocks: list[str] = []
    if prior_tail_parts:
        header = (
            _PRIOR_TAIL_HEADER_SYSTEM
            if is_system_bot
            else _PRIOR_TAIL_HEADER_ROLEPLAY
        )
        blocks.append(header + "\n" + "\n".join(prior_tail_parts))
    if semantic_parts:
        header = (
            _SEMANTIC_HEADER_SYSTEM
            if is_system_bot
            else _SEMANTIC_HEADER_ROLEPLAY
        )
        blocks.append(header + "\n" + "\n".join(semantic_parts))
    if state_parts:
        blocks.append("[Right now]\n" + "\n".join(state_parts))
    if event_parts:
        blocks.append(
            "[Since you were last here]\n"
            + "\n".join(event_parts)
        )
    if not blocks:
        return None
    return "\n\n".join(blocks)


def _store_bridge_metadata(
    conversation_id: int | None,
    prior_tail_parts: list[str],
    semantic_parts: list[str],
    user_message: str,
    chatbot_name: str,
) -> None:
    """Persist bridge retrieval results as metadata on the conversation.

    Stored as ``metadata_type: "semantic_bridge"`` entries in the
    conversation's message list so the conversation inspector can
    display them as a separate flow step.  Best-effort — failures
    are silently swallowed.
    """
    if not conversation_id:
        return
    combined = (semantic_parts or []) + (prior_tail_parts or [])
    if not combined:
        return
    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )
        import datetime as _dt

        with Conversation.objects.transaction() as tx:
            conv = (
                tx.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )
            if conv is None:
                return
            now = _dt.datetime.now(_dt.timezone.utc).isoformat()
            value = conv.value if isinstance(conv.value, list) else []
            value.append(
                {
                    "metadata_type": "semantic_bridge",
                    "timestamp": now,
                    "exchanges": combined,
                    "user_message": user_message[:200],
                    "chatbot_name": chatbot_name,
                }
            )
            conv.value = value
            tx.add(conv)
    except Exception:
        pass


def _append_concern(parts: list[str], chatbot) -> None:
    """Add the active concern if present in world_state."""
    ws = getattr(chatbot, "world_state", None) or {}
    concern = ws.get("active_concern")
    if concern:
        parts.append(f"You've been thinking about: {concern}")


def _append_voice_sample(parts: list[str], chatbot) -> None:
    """Add the most recent voice sample from past sessions."""
    samples = getattr(chatbot, "voice_samples", None) or []
    if not samples:
        return
    if isinstance(samples, list) and len(samples) > 0:
        latest = samples[-1]
        if isinstance(latest, dict):
            text = latest.get("text", "")
            if text:
                parts.append(f"You said last time: \"{text}\"")
                return
    if isinstance(samples, dict):
        text = samples.get("text", "")
        if text:
            parts.append(f"You said last time: \"{text}\"")


def _append_unsurfaced_events(parts: list[str], chatbot_id: int) -> None:
    """Add any unsurfaced story events, marking them surfaced."""
    try:
        from airunner_services.database.models.chatbot_story_event import (
            ChatbotStoryEvent,
        )

        events = (
            ChatbotStoryEvent.objects.query()
            .filter(
                ChatbotStoryEvent.chatbot_id == chatbot_id,
                ChatbotStoryEvent.surfaced.is_(False),
            )
            .order_by(ChatbotStoryEvent.occurred_at.asc())
            .limit(2)
            .all()
        )
        if not events:
            return
        lines: list[str] = []
        ids_to_surface: list[int] = []
        for event in events:
            event_type = event.event_type
            payload = event.payload or {}
            desc = _describe_event(event_type, payload)
            if desc:
                lines.append(f"While you were away: {desc}")
            ids_to_surface.append(event.id)

        # Mark events as surfaced
        for eid in ids_to_surface:
            ChatbotStoryEvent.objects.update(eid, surfaced=True)

        if lines:
            parts.extend(lines)
    except Exception:
        pass


def _append_inventory(parts: list[str], chatbot) -> None:
    """Add carried items from world_state inventory."""
    ws = getattr(chatbot, "world_state", None) or {}
    inventory = ws.get("inventory", [])
    if not inventory:
        return
    if not isinstance(inventory, list):
        return
    items = [i for i in inventory if isinstance(i, str)]
    if items:
        items_str = ", ".join(items)
        parts.append(f"You are carrying: {items_str}")


def _describe_event(event_type: str, payload: dict) -> Optional[str]:
    """Return a brief description of a story event for context injection."""
    if event_type == "item_found":
        item = (payload or {}).get("item", "something")
        return f"You found {item}."
    if event_type == "weather_event":
        desc = (payload or {}).get("desc", "")
        return f"Weather event: {desc}."
    if event_type == "encounter":
        npc = (payload or {}).get("npc_name", "someone")
        npc_type = (payload or {}).get("npc_type", "")
        type_str = f" (a {npc_type})" if npc_type else ""
        impression = (payload or {}).get("impression", "")
        imp_str = f" — {impression}" if impression else ""
        return f"You met {npc}{type_str}{imp_str}."
    if event_type == "illness":
        symptom = (payload or {}).get("symptom", "not feeling well")
        return f"You've been feeling unwell: {symptom}."
    if event_type == "milestone":
        default = "Something important happened."
        desc = (payload or {}).get("description", default)
        return f"Milestone: {desc}."
    if event_type == "relapse":
        symptom = (payload or {}).get("symptom", "not recovered")
        return f"Relapse: {symptom}."
    return None


