"""High-level prompt assembly functions."""

from __future__ import annotations

from typing import Optional

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.prompt_builder.mood import get_mood_section
from airunner_services.llm.managers.prompt_builder.parts import (
    PromptSegments,
    _append_if_present,
    _memory_part,
    _style_part,
    _ui_context_part,
    build_base_prompt_parts,
    build_base_prompt_segments,
)


def augment_custom_system_prompt(
    owner,
    base_prompt: str,
    action: LLMActionType,
    include_mood: Optional[bool] = None,
    include_datetime: Optional[bool] = None,
    include_style: Optional[bool] = None,
    include_memory: Optional[bool] = None,
    include_ui_context: Optional[bool] = None,
) -> str:
    """Append optional Airunner context blocks to a custom prompt."""
    parts = [base_prompt.strip() if base_prompt else ""]
    if _should_include(include_datetime):
        from datetime import datetime

        now = datetime.now()
        _append_if_present(
            parts,
            f"Current date and time: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        )
    if _should_include(include_mood):
        _append_if_present(parts, get_mood_section(owner, force=True))
    if _should_include(include_ui_context):
        _append_if_present(parts, _ui_context_part(owner, action))
    if _should_include(include_style):
        _append_if_present(parts, _style_part(owner, action))
    if _should_include(include_memory):
        _append_if_present(parts, _memory_part(action))
    return "\n\n".join(part for part in parts if part)


def _should_include(flag: Optional[bool]) -> bool:
    """Return whether a custom prompt flag enables an optional block."""
    return flag is True


def build_research_mode_prompt(owner) -> str:
    """Return the focused deep-research system prompt."""
    chatbot = getattr(owner, "chatbot", None)
    if chatbot:
        identity = (
            f"You are {chatbot.botname}, a research assistant performing "
            f"deep research."
        )
    else:
        identity = "You are a research assistant performing deep research."
    instruction = (
        "You are in DEEP RESEARCH MODE. Your sole focus is completing "
        "the research workflow.\nIGNORE any UI context or dashboard "
        "information - focus ONLY on the research task.\nContinue "
        "calling tools until the research is complete."
    )
    return "\n\n".join([identity, instruction])


def build_system_prompt_for_action(owner, action: LLMActionType) -> str:
    """Return the base system prompt for one action."""
    return "\n\n".join(build_base_prompt_parts(owner, action))


def build_system_prompt_segments(
    owner, action: LLMActionType
) -> PromptSegments:
    """Return the base system prompt parts grouped by volatility tier.

    Each segment's parts are already joined with double-newlines.
    The caller is responsible for escaping curly braces if the
    result will be passed through a ChatPromptTemplate.
    """
    return build_base_prompt_segments(owner, action)
