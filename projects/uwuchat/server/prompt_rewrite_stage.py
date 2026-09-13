"""Prompt-rewrite classification stage for UwUchat.

Runs before TOOL_CLASSIFICATION to detect user prompts that will
collide with pipeline limits (e.g. asking for dozens of
independently-sourced items in one turn) and rewrite them into a
scope the pipeline can actually deliver.

The rewritten prompt is used internally only — the user's original
message remains displayed and persisted unchanged.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Maximum well-sourced items the pipeline can realistically deliver
# in one turn based on _MAX_SEARCH_QUERIES=5, _MAX_TOOL_ROUNDS=4,
# and ~1 grounding source per search call.
_MAX_REALISTIC_ITEMS = 8

_CLASSIFICATION_PROMPT = (
    "You are a request classifier. Your ONLY job is to decide whether "
    "a user's message asks for an unrealistic quantity of "
    "independently-grounded items that a single-turn search pipeline "
    "cannot deliver.\n\n"
    "Rules:\n"
    "1. If the message asks for more than 8 specific, independently-"
    "verifiable items (articles, examples, sources, facts, dates, "
    "people), respond with NEEDS_REWRITE.\n"
    "2. If the message is reasonably scoped (8 or fewer items, or "
    "the items are not independently-verifiable), respond with OK.\n"
    "3. A broad research question (\"tell me about X\", \"what's the "
    "history of X\") is OK — it's asking for synthesis, not a "
    "specific count of independently-sourced items.\n"
    "4. A question asking for a specific number (\"find N articles\") "
    "is a count request — compare N to 8.\n\n"
    "Respond with EXACTLY one line: NEEDS_REWRITE or OK, followed by "
    "a colon and the rewritten prompt (for NEEDS_REWRITE) or the "
    "original message (for OK).\n\n"
    "Examples:\n"
    '  User: "What happened in the news today?"\n'
    '  OK: What happened in the news today?\n\n'
    '  User: "Find 50 different articles on a band from over the years'
    ' and tell me what you learn"\n'
    '  NEEDS_REWRITE: Find a handful of well-sourced articles on a band'
    ' covering different time periods if possible, and tell me what you'
    ' learn\n\n'
    '  User: "Tell me everything you can about a certain city"\n'
    '  OK: Tell me everything you can about a certain city\n\n'
    '  User: "Give me 20 facts about a historical figure"\n'
    '  NEEDS_REWRITE: Give me several key facts about a historical figure'
    ' covering different aspects of their life\n'
)


def build_rewrite_prompt() -> str:
    """Return the classification system prompt."""
    return _CLASSIFICATION_PROMPT


def parse_rewrite_response(
    response_text: str,
    original_prompt: str,
) -> tuple[Optional[str], str]:
    """Parse the classification model's response.

    Args:
        response_text: Raw text from the classification model.
        original_prompt: The user's original message.

    Returns:
        (rewritten_prompt | None, reason) — rewritten_prompt is
        None when no rewrite is needed; reason is a short log label.
    """
    text = response_text.strip()
    if text.startswith("OK:"):
        return None, "scope acceptable"
    if text.startswith("NEEDS_REWRITE:"):
        rewritten = text[len("NEEDS_REWRITE:"):].strip()
        if rewritten and rewritten != original_prompt:
            return rewritten, "unrealistic quantity"
        return None, "rewrite identical to original"
    # Model didn't follow format — fail open.
    logger.debug(
        "Prompt rewrite: unparseable response, failing open: %s",
        text[:80],
    )
    return None, "unparseable response"


def run_prompt_rewrite_stage(
    *,
    chat_model: Any,
    prompt: str,
) -> tuple[str, Optional[str]]:
    """Run the prompt-rewrite classification stage.

    Args:
        chat_model: The classification chat model (cheap tier).
        prompt: The user's raw prompt text.

    Returns:
        (effective_prompt, reason_or_none) — effective_prompt is the
        rewritten prompt when a rewrite is needed, otherwise the
        original.  reason_or_none is a short label for logging.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    try:
        messages = [
            SystemMessage(content=build_rewrite_prompt()),
            HumanMessage(content=prompt),
        ]
        response = chat_model.invoke(messages, max_tokens=256)
        content = getattr(response, "content", "") or ""
        rewritten, reason = parse_rewrite_response(content, prompt)
        if rewritten is not None:
            logger.info(
                "Prompt rewrite: %s — '%s' → '%s'",
                reason,
                prompt[:60],
                rewritten[:60],
            )
            return rewritten, reason
        return prompt, reason
    except Exception:
        logger.debug(
            "Prompt rewrite: classification failed, "
            "passing original prompt through",
            exc_info=True,
        )
        return prompt, None
