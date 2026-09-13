"""Unified mood-update prompt builder — per-turn and session-end."""

from __future__ import annotations

from airunner_services.llm.mood.context import (
    MoodContext,
    _truncate_on_word_boundary,
)

_MESSAGE_CAP = 200


def _format_messages(messages: list[dict]) -> str:
    """Format messages, truncating each on a word boundary."""
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "?").upper()
        content = m.get("content", "")
        truncated = _truncate_on_word_boundary(content, _MESSAGE_CAP)
        lines.append(f"{role}: {truncated}")
    return "\n".join(lines)


def _build_rules_section(name: str) -> str:
    """Return PERSPECTIVE RULES + VARIETY RULES as a single block."""
    return (
        "PERSPECTIVE RULES:\n"
        f"- You ARE {name}. Write your mood as 'I feel...'.\n"
        "- The other person is 'the user' or 'they'.\n"
        "- Their life belongs to them, not you.\n"
        "VARIETY RULES:\n"
        "- People's moods shift naturally. If the conversation has "
        "progressed, your mood should evolve \u2014 don't stay stuck.\n"
        "- If you've been feeling the same way for several turns, "
        "pick a different but still-plausible emotion.\n"
        "- Small changes count: 'curious' \u2192 'intrigued', "
        "'content' \u2192 'peaceful', 'annoyed' \u2192 'amused'."
    )


def _append_context_sections(
    parts: list[str], ctx: MoodContext,
) -> None:
    """Append optional persona/backstory/user/memory sections."""
    if ctx.persona_snippet:
        parts.append(f"Your personality: {ctx.persona_snippet}")
    if ctx.backstory_snippet:
        parts.append(f"Your backstory: {ctx.backstory_snippet}")
    if ctx.user_name:
        parts.append(f"You are talking to {ctx.user_name}.")
    if ctx.memory_snippet:
        parts.append(
            f"Your memories of this relationship: "
            f"{ctx.memory_snippet}"
        )


def _mood_line(ctx: MoodContext) -> str:
    """Return the 'last recorded mood' line."""
    return (
        f"Your last recorded mood was: "
        f"{ctx.current_mood} {ctx.current_emoji}"
    )


def _message_window(ctx: MoodContext, is_session_end: bool) -> str:
    """Return the framed message window + question."""
    text = _format_messages(ctx.messages)
    if is_session_end:
        header = (
            "You've just finished a conversation session. "
            f"Here is the full session:\n\n{text}"
        )
        question = "How do you feel now at the end of this session?"
    else:
        header = f"Recent conversation:\n{text}"
        question = "How do you feel now after this exchange?"
    return f"{header}\n\n{question}"


def _json_instruction() -> str:
    """Return the JSON-output instruction line."""
    return (
        "Return ONLY a JSON object:\n"
        '{"mood": "one word or short phrase", '
        '"emoji": "a single emoji"}'
    )


def build_mood_prompt(
    context: MoodContext,
    is_session_end: bool = False,
) -> str:
    """Build the full mood-update prompt from a MoodContext."""
    name = context.chatbot_name
    parts: list[str] = [f"You are {name}."]
    _append_context_sections(parts, context)
    parts.append(_mood_line(context))
    parts.append(_message_window(context, is_session_end))
    parts.append(_json_instruction())
    parts.append(_build_rules_section(name))
    return "\n\n".join(parts)
