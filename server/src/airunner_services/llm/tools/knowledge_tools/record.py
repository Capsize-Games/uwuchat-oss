"""Record knowledge tool.

Stores a meaningful fact about the user in the knowledge base.
"""

import re
import threading
from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import tool, ToolCategory
from airunner_services.contract_enums import SignalCode
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

_MIN_WORDS = 5
_turn_cache = threading.local()


def _turn_seen_facts() -> set:
    if not hasattr(_turn_cache, "facts"):
        _turn_cache.facts = set()
    return _turn_cache.facts


def clear_turn_cache() -> None:
    """Clear the per-turn dedup cache at the start of each generation."""
    _turn_cache.facts = set()


_NOISE_PATTERNS = re.compile(
    r"^(yo+\.?|hey+\.?|hi+\.?|hello+\.?|sup\??"
    r"|how('?ve| are| is| was)? (you|things|it going)"
    r"|you good\??"
    r"|good to (hear|see|meet)"
    r"|same as always"
    r"|thanks?( you)?"
    r"|i('ve)? been (good|well|okay|ok|fine|alright)"
    r"|how about you"
    r")[\s!.]*$",
    re.IGNORECASE,
)

def _is_low_quality(fact: str) -> bool:
    """Return True if the fact is too vague to be worth storing."""
    words = fact.strip().split()
    if len(words) < _MIN_WORDS:
        return True
    if _NOISE_PATTERNS.match(fact.strip()):
        return True
    return False

@tool(
    name="record_knowledge",
    category=ToolCategory.KNOWLEDGE,
    description=(
        "Record a SPECIFIC, MEANINGFUL fact you have learned about the user "
        "— something that would be useful to remember in future conversations. "
        "Only use this for substantive information: their name, job, health, "
        "goals, relationships, hobbies, strong opinions, or life events. "
        "DO NOT record: greetings, small talk, questions, one-word replies, "
        "acknowledgments, or anything that isn't a real fact about them. "
        "Use descriptive tags like 'Identity', 'Health', 'Work', 'Hobbies', "
        "'Relationships', 'Goals', 'Preferences'. "
        "The system skips duplicates automatically."
    ),
    return_direct=False,
    requires_api=False,
    defer_loading=False,
    keywords=[
        "remember",
        "memory",
        "fact",
        "store",
        "save",
        "learn",
        "record",
        "note",
    ],
    input_examples=[
        {"fact": "User's name is Joe Curlee", "tags": "Identity"},
        {"fact": "User has chronic back pain", "tags": "Health, Wellness"},
        {
            "fact": "User is working on AI Runner project",
            "tags": "Work, Projects",
        },
        {"fact": "User prefers dark mode", "tags": "Preferences"},
    ],
)
def record_knowledge(
    fact: Annotated[str, "The factual statement to remember about the user"],
    tags: Annotated[
        str,
        "Comma-separated topic tags (e.g. 'Relationships', 'Health, Wellness')",
    ] = "",
    source_type: Annotated[
        str,
        "Origin of this fact: 'user_stated', 'inferred', 'web_search', "
        "or 'conversation_recall'",
    ] = "",
    source_url: Annotated[
        str,
        "URL of the source when source_type is 'web_search'",
    ] = "",
    confidence: Annotated[
        float,
        "Confidence 0.0–1.0; leave blank if not assessed",
    ] = -1.0,
    entity_name: Annotated[
        str,
        "When this fact is about a specific person/entity (not the user "
        "or the character), provide their name for resolution",
    ] = "",
    entity_type: Annotated[
        str,
        "Type of the entity: person, place, thing, concept, "
        "organization, or event.  Only used when entity_name is also "
        "provided.",
    ] = "person",
    api: Any = None,
) -> str:
    """Record a meaningful fact to the knowledge base.

    If *entity_name* is provided, the fact is scoped to that resolved
    entity rather than to "user"/"self".
    """
    seen = _turn_seen_facts()
    key = fact.strip().lower()
    if key in seen:
        return (
            "DUPLICATE — this fact was already recorded this turn. "
            "Do NOT call record_knowledge again."
        )
    seen.add(key)

    if _is_low_quality(fact):
        logger.debug(
            "record_knowledge: rejected low-quality fact (%d words): %r",
            len(fact.split()),
            fact[:60],
        )
        return "Skipped: not a meaningful fact worth storing."

    # Auto-populate source metadata when a search tool ran this turn.
    resolved_type = _resolve_source_type(source_type)
    resolved_url = _resolve_source_url(source_url)
    resolved_confidence = (
        None if confidence < 0.0 else min(max(confidence, 0.0), 1.0)
    )

    try:
        from airunner_services.knowledge import get_knowledge_base
        from airunner_services.knowledge_context import \
            get_knowledge_chatbot_id
        from airunner_services.entity_resolver import (
            normalize_entity_type,
            resolve_entity,
        )

        kb = get_knowledge_base()
        embedding_model = getattr(api, "embedding", None) if api else None
        resolved_entity_id = None
        e_name = entity_name.strip() if entity_name else ""
        if e_name:
            cid = get_knowledge_chatbot_id()
            if cid is not None:
                resolved_entity_id = resolve_entity(
                    name=e_name,
                    chatbot_id=cid,
                    entity_type=normalize_entity_type(entity_type),
                    source_type="conversation",
                )

        # Normalize tags to the controlled vocabulary (Part 6).
        from airunner_services.tag_vocabulary import normalize_tags

        normalized_tags = normalize_tags(tags)

        success = kb.add_fact(
            fact,
            tags=normalized_tags or None,
            embedding_model=embedding_model,
            source_type=resolved_type,
            source_url=resolved_url or None,
            confidence=resolved_confidence,
            entity_id=resolved_entity_id,
        )

        if not success:
            return (
                "DUPLICATE — this fact is already stored. "
                "Do NOT call record_knowledge again for the same information."
            )

        tag_list = (
            [t.strip() for t in tags.split(",") if t.strip()]
            if tags
            else []
        )
        tag_label = ", ".join(tag_list) if tag_list else "untagged"

        if api and hasattr(api, "emit_signal"):
            api.emit_signal(
                SignalCode.KNOWLEDGE_FACT_ADDED,
                {"fact": fact, "tags": tag_list},
            )
        return (
            f"Recorded [{tag_label}] ({resolved_type}): "
            f"{fact[:60]}{'...' if len(fact) > 60 else ''}"
        )

    except Exception as e:
        logger.error("Error recording knowledge: %s", e)
        return f"Error: {str(e)}"


def _resolve_source_type(model_supplied: str) -> str:
    """Determine the best source_type for a fact being recorded.

    If the model didn't specify a source_type and a SEARCH tool ran this
    turn (detected via the grounding cache), default to 'web_search'.
    Otherwise use the model-supplied value or fall back to 'user_stated'.
    """
    if model_supplied and model_supplied.strip():
        return model_supplied.strip()
    from airunner_services.llm.tools.grounding_tools_helpers import (
        get_grounding_sources,
    )
    sources = get_grounding_sources()
    if sources:
        return "web_search"
    return "user_stated"


def _resolve_source_url(model_supplied: str) -> str:
    """Determine the best source_url for a fact being recorded.

    When the model did not supply a URL but search tools ran this turn,
    extract the first HTTP URL found in the grounding cache's captured
    search results.  This follows the same principle as
    _resolve_source_type: the pipeline determines it, not the LLM.
    """
    if model_supplied and model_supplied.strip():
        return model_supplied.strip()
    from airunner_services.llm.tools.grounding_tools_helpers import (
        get_grounding_sources,
    )
    _url_re = re.compile(r"https?://[^\s\"'<>),;]+")
    for source in get_grounding_sources():
        m = _url_re.search(source)
        if m:
            return m.group(0)
    return ""
