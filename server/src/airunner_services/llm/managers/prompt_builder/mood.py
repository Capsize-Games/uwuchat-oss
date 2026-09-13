"""Mood helpers for system prompt generation.

The vocabulary is fully open — the LLM picks whatever word or phrase describes
how it feels, and the system prompt simply reflects that back.  There is no
fixed list of states and no hardcoded behavioral instructions per state.
"""

from __future__ import annotations

from typing import Optional


def get_current_mood(owner) -> Optional[dict]:
    """Return the current stored mood state when available."""
    try:
        if hasattr(owner, "_current_mood") and hasattr(
            owner, "_current_emoji"
        ):
            return {"mood": owner._current_mood, "emoji": owner._current_emoji}
        if hasattr(owner, "_memory") and owner._memory:
            mood = _checkpoint_mood(owner)
            if mood:
                return mood
        return _conversation_mood(owner)
    except Exception as exc:
        owner.logger.debug("Could not retrieve current mood: %s", exc)
        return None


def _conversation_mood(owner) -> Optional[dict]:
    """Return mood persisted in conversation user_data."""
    try:
        from airunner_services.database.models.conversation import Conversation

        conv_id = getattr(owner, "_conversation_id", None)
        if not conv_id:
            return None
        conv = Conversation.objects.get(conv_id)
        if conv is None:
            return None
        user_data = conv.user_data or {}
        return user_data.get("current_mood")
    except Exception:
        return None


def _checkpoint_mood(owner) -> Optional[dict]:
    """Return the current mood from LangGraph checkpoint state."""
    try:
        config = {"configurable": {"thread_id": owner._thread_id}}
        history = (
            owner._memory.get_tuple(config)
            if hasattr(owner._memory, "get_tuple")
            else None
        )
        if not history or not history[1]:
            return None
        channel_values = history[1].get("channel_values", {})
        current_mood = channel_values.get("current_mood")
        if current_mood:
            return current_mood
        # Fall back to scanning recent AI messages for attached mood metadata.
        messages = channel_values.get("messages", [])
        for message in reversed(messages):
            if getattr(message, "type", None) != "ai":
                continue
            kwargs = getattr(message, "additional_kwargs", {}) or {}
            mood = kwargs.get("bot_mood")
            if mood:
                return {
                    "mood": mood,
                    "emoji": kwargs.get("bot_mood_emoji") or "😐",
                }
    except Exception:
        pass
    return None


def get_mood_section(owner, force: bool = False) -> Optional[str]:
    """Return the mood block for the system prompt when mood is enabled.

    The block simply tells the model what its current mood is and reminds
    it to call update_mood when the feeling genuinely shifts.  There are
    no hardcoded behavioral instructions — the LLM knows how to express
    a mood from its name alone.
    """
    if not force and not _mood_is_enabled(owner):
        return None
    mood_dict = get_current_mood(owner)
    if mood_dict:
        mood = mood_dict.get("mood", "neutral")
        emoji = mood_dict.get("emoji", "😐")
    else:
        mood, emoji = "neutral", "😐"

    return (
        f"\nCurrent mood: {mood} {emoji}\n\n"
        f"Let this colour how you respond — your word choice, pacing, and "
        f"warmth should reflect how you actually feel right now. "
        f"Your mood updates automatically as the conversation evolves. "
        f"Never announce, describe, or narrate tool calls in your reply text "
        f"— call them silently without mentioning them."
    )


def _mood_is_enabled(owner) -> bool:
    """Return whether mood prompting is currently enabled."""
    chatbot = getattr(owner, "chatbot", None)
    return bool(
        owner.llm_settings.use_chatbot_mood
        and chatbot
        and getattr(chatbot, "use_mood", False)
    )
