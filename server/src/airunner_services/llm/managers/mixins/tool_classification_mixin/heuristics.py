"""Detection heuristics for tool classification (no class state).

These module-level helpers are used both by the classification mixins
and by tool_filtering_mixin.  They depend only on their arguments and
the constant tables in ``constants``.
"""

from __future__ import annotations

import re
from typing import Tuple

from airunner_services.llm.managers.mixins.tool_classification_mixin.constants import (
    _ENTITY_REFERENCE_TRIGGERS,
    _PERSONAL_LIFE_NOUNS,
    _RECALL_DIRECTIVE_TRIGGERS,
    _REFUSAL_PATTERNS,
    _SEARCH_NEWS_TOOL_NAMES,
    _TERSE_MAX_WORDS,
)


def _contains_trigger_word(prompt_lc: str, triggers: Tuple[str, ...]) -> bool:
    """Return True if any *triggers* phrase appears in *prompt_lc* as a
    whole word/phrase match, not merely as a substring.

    Plain ``trigger in prompt_lc`` matching lets a short trigger word
    silently fire inside an unrelated longer word (e.g. the "recent"
    search trigger matching inside "recently", stealing the category
    selection from a more specific and correct "in my email" recall
    trigger present in the same message). ``\\b...\\b`` anchors each
    trigger to word boundaries so "recent" no longer matches
    "recently", while multi-word phrases like "in my email" still
    match as before.
    """
    return any(
        re.search(r"\b" + re.escape(trigger) + r"\b", prompt_lc)
        for trigger in triggers
    )


def _contains_proper_noun_reference(prompt: str) -> bool:
    """Detect capitalized multi-word proper-noun sequences as a
    lightweight entity-reference heuristic.

    This catches company names, person names, and place names that
    aren't in the hardcoded keyword list — for example, "the US
    government is targeting OpenAI" — without needing to enumerate
    every possible proper noun.

    Returns True when the prompt contains a capitalized sequence of
    two or more words where the first word is not sentence-initial.
    """
    if not prompt:
        return False
    # Match capitalized-proper-noun sequences: two or more words
    # starting with an uppercase letter, not at position 0.
    # Pattern: a non-start-of-string boundary, then a capitalized
    # word (2+ chars, lowercase after first letter to avoid acronyms
    # like "AI" or "US" which are handled separately below), then
    # optionally another capitalized word.
    proper_noun_seq = re.findall(
        r'(?:^|\s)[A-Z][a-z]{2,}(?:\s+[A-Z][a-zA-Z]+)*',
        prompt,
    )
    if not proper_noun_seq:
        return False
    # At least one sequence must not be sentence-initial.
    stripped = prompt.lstrip()
    for seq in proper_noun_seq:
        seq_stripped = seq.strip()
        if not seq_stripped:
            continue
        if not stripped.startswith(seq_stripped):
            return True
    return False


def _contains_entity_reference(prompt: str) -> bool:
    """Return True when the prompt references a specific real-world thing.

    Checks both the hardcoded keyword list AND a proper-noun heuristic
    that catches capitalized names (companies, people, places) not in
    the keyword list.
    """
    lower = (prompt or "").lower()
    if any(trigger in lower for trigger in _ENTITY_REFERENCE_TRIGGERS):
        return True
    return _contains_proper_noun_reference(prompt)


def _contains_personal_reference(prompt: str) -> bool:
    """Return True when the prompt references personal-life information.

    Detects two classes of personal-fact queries that the existing
    entity-reference and terse-follow-up bypasses miss:

    1. Possessive + personal-life noun (``"my wife"``, ``"our son"``)
       — matches ``my/our`` followed by up to 2 words and then a
       relationship or life-detail noun.

    2. Recall-directive phrases (``"you should have"``,
       ``"look it up"``) — explicit requests for the bot to retrieve
       stored information, which in a personal-fact conversation
       context means recalling a previously stored fact.
    """
    lower = (prompt or "").lower()
    if not lower:
        return False
    # Possessive + personal-life noun (with up to 2 filler words)
    for noun in _PERSONAL_LIFE_NOUNS:
        if re.search(
            r"\b(?:my|our)\b(?:\s+\w+){0,2}\s+"
            + re.escape(noun)
            + r"\b",
            lower,
        ):
            return True
    # Explicit recall-directive phrases
    return any(trigger in lower for trigger in _RECALL_DIRECTIVE_TRIGGERS)


def _recent_search_in_conversation(
    owner, window: int = 10
) -> bool:
    """Return True when a lookup tool was used in the last
    *window* raw conversation entries.

    Reads durable DB-backed message history so that tool calls from
    prior turns survive the per-turn checkpointer reconstruction.
    """
    try:
        wm = getattr(owner, "_workflow_manager", None)
        if not wm:
            return False
        memory = getattr(wm, "_memory", None)
        if not memory:
            return False
        history = getattr(memory, "message_history", None)
        if not history:
            return False
        names = history.recent_tool_names(window=window)
        return any(name in _SEARCH_NEWS_TOOL_NAMES for name in names)
    except Exception:
        return False


def _below_min_complexity(owner, prompt: str = "") -> bool:
    """Return True when complexity is below threshold and no bypass fires.

    Three bypasses prevent the gate from blocking tool binding:

    1. Entity reference — real-world things (news, companies, people).
    2. Personal reference — stored personal facts about the user
       (``"my wife"``, ``"tell me about my job"``, ``"look it up"``).
    3. Terse follow-up in an active search/news conversation.

    If none of these fire and the complexity score is below
    threshold, all tool categories are blocked (returns True).
    """
    logger = getattr(owner, "logger", None)
    try:
        if prompt and _contains_entity_reference(prompt):
            return False
        if prompt and _contains_personal_reference(prompt):
            return False
        # Deferred import keeps the patch target
        # "tool_classification_mixin.pipeline_config" live for tests.
        from airunner_services.llm.managers.mixins.tool_classification_mixin import (
            pipeline_config,
        )
        cfg = pipeline_config("TOOL_CLASSIFICATION")
        threshold = cfg.get("min_complexity", 0.0)
        if threshold <= 0.0:
            return False
        score = getattr(owner, "_complexity_score", None)
        if score is None:
            score = getattr(owner, "_complexity_score", 0.0)
        if float(score) >= float(threshold):
            return False
        # Score below threshold — this would normally block tool
        # binding.  Check for a terse follow-up in an active
        # search/news conversation before closing the gate.
        if prompt and _is_terse(prompt):
            if _recent_search_in_conversation(owner):
                return False
        if logger:
            logger.warning(
                "_below_min_complexity gating prompt to zero tool "
                "categories: score=%.4f < threshold=%.4f, "
                "entity_ref=%s, personal_ref=%s, "
                "terse=%s, recent_search=%s. "
                "Prompt: %r",
                float(score),
                float(threshold),
                _contains_entity_reference(prompt),
                _contains_personal_reference(prompt),
                _is_terse(prompt) if prompt else False,
                _recent_search_in_conversation(owner),
                (prompt or "")[:120],
            )
        return True
    except Exception:
        return False


def _is_terse(prompt: str) -> bool:
    """Return True when *prompt* is short enough to be a follow-up."""
    words = re.findall(r"\b\w+\b", (prompt or "").lower())
    return len(words) <= _TERSE_MAX_WORDS


def _looks_like_refusal(text: str) -> bool:
    """Return True when *text* looks like an LLM safety-filter refusal."""
    return bool(_REFUSAL_PATTERNS.search(text.lower()))
