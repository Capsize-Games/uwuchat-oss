"""Record a fact about the character itself (self-knowledge tool)."""

import re
from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import ToolCategory, tool
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

_MIN_WORDS = 5
_NOISE_PATTERNS = re.compile(
    r"^(same as always|good to (hear|see)|yeah|yep|nope|okay|ok|fine"
    r"|i('ve)? been (good|well|okay|ok|fine|alright)"
    r")[\s!.]*$",
    re.IGNORECASE,
)


def _is_low_quality(fact: str) -> bool:
    """Return True if the fact is too vague or transient to store."""
    words = fact.strip().split()
    if len(words) < _MIN_WORDS:
        return True
    return bool(_NOISE_PATTERNS.match(fact.strip()))


@tool(
    name="record_character_fact",
    category=ToolCategory.KNOWLEDGE,
    description=(
        "Record a SPECIFIC, DURABLE fact about yourself — something you've "
        "established, invented, or revealed that should stay consistent "
        "across future conversations. Use this for established traits, "
        "backstory, relationships, or invented details about your life. "
        "DO NOT record: casual observations, conversational remarks, "
        "scene descriptions from a single moment, or anything that wouldn't "
        "matter in future sessions."
    ),
    return_direct=False,
    requires_api=False,
    defer_loading=False,
    keywords=[
        "remember myself",
        "my fact",
        "about me",
        "i am",
        "i live",
        "my home",
        "my past",
        "who i am",
    ],
    input_examples=[
        {"fact": "I live near a quiet pond in Oregon", "tags": "Location"},
        {
            "fact": "My best friend is a dragonfly named Zephyr",
            "tags": "Relationships",
        },
        {"fact": "I have never left my pond", "tags": "History"},
        {"fact": "I love catching flies at dusk", "tags": "Preferences"},
    ],
)
def record_character_fact(
    fact: Annotated[str, "The fact about yourself to remember"],
    tags: Annotated[
        str,
        "Comma-separated topic tags (e.g. 'Location', 'Family, History')",
    ] = "",
    api: Any = None,
) -> str:
    """Record a fact about the character itself.

    Args:
        fact: The self-referential fact to record.
        tags: Comma-separated topic tags.
        api: API instance (injected).

    """
    if _is_low_quality(fact):
        logger.debug(
            "record_character_fact: rejected low-quality fact: %r", fact[:60]
        )
        return "Skipped: not a durable character fact worth storing."

    from airunner_services.knowledge_context import (
        set_knowledge_subject,
    )

    set_knowledge_subject("self")
    try:
        from airunner_services.knowledge import get_knowledge_base

        kb = get_knowledge_base()
        embedding_model = getattr(api, "embedding", None) if api else None
        success = kb.add_fact(
            fact, tags=tags or None, embedding_model=embedding_model
        )

        if not success:
            return f"Already known (skipped duplicate): {fact[:50]}..."

        tag_list = (
            [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        )
        tag_label = ", ".join(tag_list) if tag_list else "untagged"
        return (
            f"Recorded about myself [{tag_label}]: "
            f"{fact[:60]}{'...' if len(fact) > 60 else ''}"
        )

    except Exception as e:
        logger.error("Error recording character fact: %s", e)
        return f"Error: {str(e)}"
    finally:
        set_knowledge_subject("user")
