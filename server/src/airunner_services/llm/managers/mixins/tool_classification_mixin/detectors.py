"""Trigger-word detection methods for the tool classification mixin."""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from airunner_services.llm.managers.mixins.tool_classification_mixin.constants import (
    _LOOKUP_TOOL_CATEGORY,
)
from airunner_services.llm.managers.mixins.tool_classification_mixin.heuristics import (
    _contains_trigger_word,
)


class ToolClassificationDetectorsMixin:
    """Detect whether a prompt requests a specific tool category.

    Inherited by the composed ``ToolClassificationMixin``; the trigger
    tables live on ``ToolClassificationPatternsMixin`` in the same MRO.
    """

    @classmethod
    def _has_math_trigger_prompt(cls, prompt: str) -> bool:
        """Return True when a prompt looks like an arithmetic/math problem.

        Combines keyword triggers with a numeric-density fallback,
        since plain word problems ("A farmer has 17 sheep...") often
        contain no math-specific vocabulary at all -- just numbers and
        ordinary words -- which the complexity scorer has no signal
        for and would otherwise score below the classification
        threshold, silently skipping the math tool category.
        """
        prompt_lc = (prompt or "").strip().lower()
        if not prompt_lc:
            return False
        if _contains_trigger_word(prompt_lc, cls.MATH_TRIGGER_WORDS):
            return True
        # Exclude digit groups directly prefixed by '#' or ':' with no
        # space — issue references ("#115") and file:line references
        # ("webhook.py:161") aren't arithmetic operands, but plain word
        # problems ("17 sheep... 8 more") never use that adjacency.
        digit_groups = re.findall(r"(?<![#:])\d+", prompt_lc)
        return len(digit_groups) >= 2

    @classmethod
    def _detect_simple_tool_route(
        cls,
        prompt: str,
    ) -> Tuple[Optional[List[str]], Optional[str]]:
        """Detect trivial prompts that should call a single tool."""
        prompt_lc = (prompt or "").strip().lower()
        if not prompt_lc:
            return None, None

        for pattern, tool_name in cls.SIMPLE_SYSTEM_TOOL_PATTERNS:
            if re.search(pattern, prompt_lc):
                return ["system"], tool_name

        return None, None

    @classmethod
    def _is_simple_greeting_prompt(cls, prompt: str) -> bool:
        """Return True for trivial greeting-style prompts."""
        prompt_lc = (prompt or "").strip().lower()
        if not prompt_lc or len(prompt_lc) > 40:
            return False

        return any(
            re.match(pattern, prompt_lc)
            for pattern in cls.SIMPLE_GREETING_PATTERNS
        )

    @classmethod
    def _is_simple_no_tool_prompt(cls, prompt: str) -> bool:
        """Return True for casual prompts that should avoid tools."""
        prompt_lc = (prompt or "").strip().lower()
        if not prompt_lc or len(prompt_lc) > 120:
            return False

        return any(
            re.match(pattern, prompt_lc)
            for pattern in cls.SIMPLE_NO_TOOL_PATTERNS
        )

    @classmethod
    def _is_constrained_reply_prompt(cls, prompt: str) -> bool:
        """Return True for strict reply-shape prompts needing no tools."""
        prompt_lc = re.sub(r"^\s*/no_think\s*", "", (prompt or "").lower())
        prompt_lc = prompt_lc.strip()
        if not prompt_lc or len(prompt_lc) > 160:
            return False
        if not re.match(r"^(?:reply|respond)\s+with\b", prompt_lc):
            return False
        return any(hint in prompt_lc for hint in cls.CONSTRAINED_REPLY_HINTS)

    @classmethod
    def _has_search_trigger_prompt(cls, prompt: str) -> bool:
        """Return True when a prompt clearly requests search tools."""
        prompt_lc = (prompt or "").strip().lower()
        return _contains_trigger_word(prompt_lc, cls.SEARCH_TRIGGER_WORDS)

    @classmethod
    def _is_image_generation_prompt(cls, prompt: str) -> bool:
        """Return True when a prompt requests image or picture generation."""
        prompt_lc = (prompt or "").strip().lower()
        return _contains_trigger_word(prompt_lc, cls.IMAGE_TRIGGER_WORDS)

    @classmethod
    def _has_calendar_trigger_prompt(cls, prompt: str) -> bool:
        """Return True when a prompt requests calendar/reminder tools."""
        prompt_lc = (prompt or "").strip().lower()
        return _contains_trigger_word(prompt_lc, cls.CALENDAR_TRIGGER_WORDS)

    @classmethod
    def _has_recall_trigger_prompt(cls, prompt: str) -> bool:
        """Return True when a prompt requests past-conversation recall."""
        prompt_lc = (prompt or "").strip().lower()
        return _contains_trigger_word(prompt_lc, cls.RECALL_TRIGGER_WORDS)

    @classmethod
    def _has_weather_trigger_prompt(cls, prompt: str) -> bool:
        """Return True when a prompt requests weather/forecast tools."""
        prompt_lc = (prompt or "").strip().lower()
        return _contains_trigger_word(prompt_lc, cls.WEATHER_TRIGGER_WORDS)

    @classmethod
    def _is_retry_phrase(cls, prompt: str) -> bool:
        """Return True when the prompt is a retry/continuation request."""
        prompt_lc = (prompt or "").strip().lower()
        return _contains_trigger_word(prompt_lc, cls.RETRY_PHRASE_TRIGGERS)

    @classmethod
    def _recent_lookup_category(cls, owner: Any) -> Optional[str]:
        """Return the category of the most recent lookup tool, or None.

        Reads durable DB-backed message history so that tool calls
        from prior turns survive the per-turn checkpointer
        reconstruction.
        """
        try:
            wm = getattr(owner, "_workflow_manager", None)
            if not wm:
                return None
            memory = getattr(wm, "_memory", None)
            if not memory:
                return None
            history = getattr(memory, "message_history", None)
            if not history:
                return None
            names = history.recent_tool_names(window=10)
            for name in names:
                if name in _LOOKUP_TOOL_CATEGORY:
                    return _LOOKUP_TOOL_CATEGORY[name]
            return None
        except Exception:
            return None

    @classmethod
    def _should_disable_thinking_for_prompt(
        cls,
        prompt: str,
        selected_categories: Optional[List[str]] = None,
        force_tool: Optional[str] = None,
    ) -> bool:
        """Return True when reasoning adds latency but little value."""
        if force_tool:
            return True
        if cls._is_simple_greeting_prompt(prompt):
            return True
        if selected_categories == [] and len((prompt or "").strip()) <= 40:
            return True
        return False
