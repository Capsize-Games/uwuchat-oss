"""Per-turn cache for grounding sources collected from tool results.

Uses a ContextVar so concurrent conversations never cross-contaminate.
Follows the safe pattern from mood_tools.py and social_tools.py:
default=None, always .set() fresh values, never mutate in place.
"""

from contextvars import ContextVar
from typing import List, Optional

_grounding_sources: ContextVar[Optional[List[str]]] = ContextVar(
    "grounding_sources", default=None
)


def add_grounding_source(text: str) -> None:
    """Append one grounding source string for the current turn."""
    sources = list(_grounding_sources.get() or [])
    sources.append(text)
    _grounding_sources.set(sources)


def get_grounding_sources() -> List[str]:
    """Return all grounding source strings accumulated this turn."""
    return list(_grounding_sources.get() or [])


def clear_grounding_sources() -> None:
    """Reset the grounding source cache for a new turn."""
    _grounding_sources.set(None)
