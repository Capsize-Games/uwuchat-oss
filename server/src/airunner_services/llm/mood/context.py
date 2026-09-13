"""Mood context assembly — MoodContext dataclass and field builders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

_PERSONA_CAP = 200
_BACKSTORY_CAP = 150
_MEMORY_CAP = 200
_MESSAGE_CAP = 200


@dataclass
class MoodContext:
    """Pre-assembled context bundle for the mood-update prompt."""

    chatbot_name: str
    current_mood: str = "neutral"
    current_emoji: str = "😐"
    persona_snippet: str = ""
    backstory_snippet: str = ""
    user_name: str = ""
    memory_snippet: str = ""
    messages: list[dict] = field(default_factory=list)


def _truncate_on_word_boundary(text: str, max_chars: int) -> str:
    """Truncate *text* at the last word boundary before *max_chars*."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    boundary = truncated.rfind(" ")
    if boundary > 0:
        return truncated[:boundary].rstrip() + "\u2026"
    return truncated.rstrip() + "\u2026"


def _snippet(text: str, cap: int) -> str:
    """Trim *text* to *cap* chars on a word boundary, or return ''."""
    if not text or not text.strip():
        return ""
    return _truncate_on_word_boundary(text.strip(), cap)


def _extract_memory_text(row) -> Optional[str]:
    """Decrypt and return AgentMemory.summary, or None if empty."""
    if row is None:
        return None
    summary = getattr(row, "summary", None)
    if summary is None:
        return None
    text = str(summary) if summary else ""
    return text if text.strip() else None


def _fetch_agent_memory(chatbot_id: int) -> Optional[str]:
    """Return the AgentMemory.summary text for *chatbot_id*."""
    try:
        from airunner_services.database.models.agent_memory import (
            AgentMemory,
        )
        row = (
            AgentMemory.objects.query()
            .filter(AgentMemory.chatbot_id == chatbot_id)
            .first()
        )
        return _extract_memory_text(row)
    except Exception:
        return None


def _fill_persona(ctx: MoodContext, chatbot) -> None:
    """Set persona_snippet if use_personality is enabled."""
    if getattr(chatbot, "use_personality", False):
        persona = getattr(chatbot, "bot_personality", "")
        ctx.persona_snippet = _snippet(persona, _PERSONA_CAP)


def _fill_backstory(ctx: MoodContext, chatbot) -> None:
    """Set backstory_snippet if use_backstory is enabled."""
    if getattr(chatbot, "use_backstory", False):
        backstory = getattr(chatbot, "backstory", "")
        ctx.backstory_snippet = _snippet(backstory, _BACKSTORY_CAP)


def _fill_user_name(ctx: MoodContext, conversation) -> None:
    """Set user_name from conversation, if non-empty."""
    if conversation is None:
        return
    user_name = getattr(conversation, "user_name", "")
    if user_name and user_name.strip():
        ctx.user_name = user_name.strip()


def _fill_memory(ctx: MoodContext, chatbot) -> None:
    """Set memory_snippet from AgentMemory, if a row exists."""
    chatbot_id = getattr(chatbot, "id", None)
    if chatbot_id is None:
        return
    memory_text = _fetch_agent_memory(chatbot_id)
    if memory_text:
        ctx.memory_snippet = _snippet(memory_text, _MEMORY_CAP)


def _make_base_ctx(chatbot, mood_dict: dict, msgs: list[dict]) -> MoodContext:
    """Create a MoodContext with the non-optional fields populated."""
    return MoodContext(
        chatbot_name=getattr(chatbot, "botname", ""),
        current_mood=mood_dict.get("mood", "neutral"),
        current_emoji=mood_dict.get("emoji", "\U0001f610"),
        messages=msgs,
    )


def build_mood_context(
    chatbot,
    conversation,
    messages: list[dict],
    current_mood_dict: dict,
) -> MoodContext:
    """Assemble a MoodContext — empty fields when data is missing."""
    ctx = _make_base_ctx(chatbot, current_mood_dict, messages)
    if chatbot is None:
        return ctx
    _fill_persona(ctx, chatbot)
    _fill_backstory(ctx, chatbot)
    _fill_user_name(ctx, conversation)
    _fill_memory(ctx, chatbot)
    return ctx
