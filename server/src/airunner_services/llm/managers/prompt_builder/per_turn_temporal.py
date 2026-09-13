"""Per-turn temporal gap context — time-since-last-interaction.

Moved from per_turn_context.py to keep that file under the 250-line
limit while still providing the LLM with a temporal orientation signal
when the conversation has been idle for more than an hour.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.prompt_builder.prompt_builder import (
    DATETIME_ACTIONS,
)


def temporal_gap_part(owner, action: LLMActionType) -> Optional[str]:
    """Return a temporal gap line so the LLM knows how much time has passed.

    Always provides the elapsed time since the last interaction, even
    for short gaps (minutes).  This gives the LLM temporal awareness
    so it can respond realistically to the passage of time.
    """
    if action not in DATETIME_ACTIONS:
        return None
    chatbot = getattr(owner, "chatbot", None)
    chatbot_id = getattr(chatbot, "id", None) if chatbot else None
    if not chatbot_id:
        return None
    try:
        gap_hours = _compute_conversation_gap(chatbot_id)
        if gap_hours is None:
            return None
        label = _hours_ago_label(gap_hours)
        return f"Time since your last interaction with the user: {label}"
    except Exception:
        return None


def _compute_conversation_gap(chatbot_id: int) -> Optional[float]:
    """Return hours since the last visible message in the conversation."""
    conv = _latest_conversation(chatbot_id)
    if not conv:
        return None
    messages = getattr(conv, "value", None) or []
    last_ts = _last_visible_timestamp(messages)
    if not last_ts:
        return None
    return _hours_since_timestamp(last_ts)


def _latest_conversation(chatbot_id: int):
    """Return the newest Conversation for a chatbot, or None."""
    from airunner_services.database.models.conversation import (
        Conversation,
    )

    return (
        Conversation.objects.query()
        .filter(Conversation.chatbot_id == chatbot_id)
        .order_by(Conversation.id.desc())
        .first()
    )


def _hours_since_timestamp(ts: str) -> Optional[float]:
    """Return hours elapsed since an ISO-format timestamp string."""
    from datetime import timezone

    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - dt).total_seconds()
    return elapsed / 3600.0


def _last_visible_timestamp(messages: list) -> Optional[str]:
    """Return the timestamp of the last non-metadata message."""
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        if msg.get("metadata_type") in ("tool_calls", "tool_result"):
            continue
        ts = msg.get("timestamp")
        if ts:
            return ts
    return None


def _elapsed_gap_label(hours: float) -> str:
    """Return a human-friendly elapsed time string for temporal gaps."""
    return _hours_ago_label(hours)


def _hours_ago_label(hours: float) -> str:
    """Return a human-friendly 'N hours/days ago' label."""
    if hours < 0.02:
        return "just now"
    if hours < 1:
        mins = int(hours * 60)
        return f"{mins} minute{'s' if mins > 1 else ''} ago"
    if hours < 2:
        return "about an hour ago"
    if hours < 24:
        return f"about {int(hours)} hours ago"
    days = int(hours / 24)
    if days == 1:
        return "about a day ago"
    if days < 7:
        return f"about {days} days ago"
    weeks = int(days / 7)
    if weeks == 1:
        return "about a week ago"
    return f"about {weeks} weeks ago"


def relative_time_ago(iso_timestamp: str) -> str:
    """Return a human-friendly relative time label for an ISO timestamp.

    Example: ``"2026-06-25T14:30:00"`` → ``"about 2 days ago"``.
    Returns ``"unknown"`` when the timestamp cannot be parsed.
    """
    if not iso_timestamp:
        return "unknown"
    hours = _hours_since_timestamp(iso_timestamp)
    if hours is None:
        return "unknown"
    return _hours_ago_label(hours)
