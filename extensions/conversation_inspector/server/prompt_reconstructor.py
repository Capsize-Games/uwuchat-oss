"""Reconstruct system prompts for a given conversation and chatbot config.

Creates a lightweight owner adapter that satisfies the interfaces expected
by the core prompt builder, then calls the same builder functions the agent
would have used at runtime.
"""

from __future__ import annotations

from typing import Optional

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.prompt_builder.parts import (
    build_base_prompt_parts,
)
from airunner_services.llm.managers.prompt_builder.mood import (
    get_mood_section,
)
from airunner_services.llm.managers.prompt_builder.prompt_builder import (
    CONVERSATIONAL_ACTIONS,
    DATETIME_ACTIONS,
)


class _PromptOwnerAdapter:
    """Lightweight adapter satisfying the prompt builder 'owner' interface."""

    def __init__(
        self,
        *,
        chatbot=None,
        llm_settings=None,
        current_mood: Optional[dict] = None,
        current_emoji: Optional[str] = None,
    ):
        self.chatbot = chatbot
        self.llm_settings = llm_settings
        self._current_mood = current_mood
        self._current_emoji = current_emoji

    def _get_ui_section_context(self) -> Optional[str]:
        """UI context injection is disabled after the home/art split."""
        return None

    def _get_memory_context(self, _user_query: Optional[str] = None) -> str:
        """Return empty memory context — RAG is handled separately."""
        return ""

    def _get_mood_section(self, force: bool = False) -> Optional[str]:
        """Return the mood section when mood prompting is enabled."""
        return get_mood_section(self, force=force)


def _default_llm_settings():
    """Return a default LLMSettings instance."""
    from airunner_services.llm.llm_settings import LLMSettings
    return LLMSettings()


def reconstruct_system_prompt(
    chatbot=None,
    llm_settings=None,
    action: LLMActionType = LLMActionType.CHAT,
    current_mood: Optional[dict] = None,
    current_emoji: Optional[str] = None,
) -> dict:
    """Reconstruct the stable system prompt the agent would have sent.

    Since the prompt-caching refactor this prompt no longer contains
    datetime, mood, or preflight — those move to per-turn context.
    The ``is_cache_stable`` flag confirms this.

    Returns a dict with:
      - full_text: Complete system prompt string
      - parts: Dict mapping part names to their text
      - is_cache_stable: Always True (datetime/mood/preflight removed)
      - includes_mood: Always False (moved to per-turn context)
      - includes_datetime: Always False (moved to per-turn context)
      - includes_style/memory/health: Whether those sections are present
    """
    if llm_settings is None or not hasattr(llm_settings, "use_chatbot_mood"):
        llm_settings = _default_llm_settings()

    owner = _PromptOwnerAdapter(
        chatbot=chatbot,
        llm_settings=llm_settings,
        current_mood=current_mood,
        current_emoji=current_emoji,
    )

    raw_parts = build_base_prompt_parts(owner, action)

    part_map: dict[str, str] = {}
    for part in raw_parts:
        if not part:
            continue
        if "You are " in part and "personality" not in part.lower():
            part_map["identity"] = part
        elif "Embody the following personality" in part:
            part_map["personality"] = part
        elif "Style and tone guidelines" in part:
            part_map["style_guidelines"] = part
        elif "MEMORY & KNOWLEDGE INSTRUCTIONS" in part:
            part_map["memory_instructions"] = part
        elif "HEALTH & MEDICAL DISCLAIMER" in part:
            part_map["health_disclaimer"] = part
        else:
            existing = part_map.get("other", "")
            part_map["other"] = f"{existing}\n\n{part}".strip()

    full_text = "\n\n".join(part for part in raw_parts if part)

    return {
        "full_text": full_text,
        "parts": part_map,
        "is_cache_stable": True,
        "includes_mood": False,
        "includes_datetime": False,
        "includes_style": "style_guidelines" in part_map,
        "includes_memory": "memory_instructions" in part_map,
        "includes_health": "health_disclaimer" in part_map,
    }


def reconstruct_per_turn_context(
    chatbot=None,
    llm_settings=None,
    action: LLMActionType = LLMActionType.CHAT,
    current_mood: Optional[dict] = None,
    current_emoji: Optional[str] = None,
    user_message_timestamp: Optional[str] = None,
) -> dict:
    """Reconstruct the per-turn context injected into the human message.

    This is the dynamic content that was removed from the system prompt so
    the provider prefix cache is never invalidated.  It includes datetime,
    mood, and preflight (preflight is ephemeral and cannot be reconstructed,
    so it is noted as dynamic).

    Returns a dict with:
      - full_text: Reconstructed context block (best-effort)
      - parts: Dict mapping component names to their text
      - has_datetime: Whether datetime was injected this turn
      - has_mood: Whether a mood block was injected this turn
      - has_preflight_dynamic: Always True (noted as dynamic/ephemeral)
      - injection_target: "human_turn" (confirms where this content goes)
    """
    if llm_settings is None or not hasattr(llm_settings, "use_chatbot_mood"):
        llm_settings = _default_llm_settings()

    owner = _PromptOwnerAdapter(
        chatbot=chatbot,
        llm_settings=llm_settings,
        current_mood=current_mood,
        current_emoji=current_emoji,
    )

    parts: dict[str, str] = {}

    if action in DATETIME_ACTIONS:
        ts_display = user_message_timestamp or "(current request time)"
        parts["datetime"] = f"Current date and time: {ts_display}"

    if action in CONVERSATIONAL_ACTIONS:
        mood_text = get_mood_section(owner)
        if mood_text:
            parts["mood"] = mood_text.strip()

    parts["preflight"] = (
        "[PREFLIGHT INTERCEPT — dynamic per message]\n"
        "Crisis and deflect safety blocks are classified at request time "
        "and injected here when triggered. Not stored — ephemeral."
    )

    full_text = "\n\n".join(parts.values())

    return {
        "full_text": full_text,
        "parts": parts,
        "has_datetime": "datetime" in parts,
        "has_mood": "mood" in parts,
        "has_preflight_dynamic": True,
        "injection_target": "human_turn",
        "note": (
            "Injected as a prefix block on the last HumanMessage so the "
            "system prompt remains byte-for-byte identical across requests, "
            "preserving the provider prefix cache."
        ),
    }
