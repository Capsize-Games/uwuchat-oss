"""Controlled tag vocabulary for knowledge facts.

Prevents tag sprawl by normalizing free-text tags to a fixed set.
Tags outside the vocabulary are mapped case-insensitively to the
nearest known tag or rejected.
"""
from __future__ import annotations

# Ordered by relevance for display.
_VOCABULARY = [
    "Identity",
    "Health",
    "Work",
    "Relationships",
    "Goals",
    "Preferences",
    "Hobbies",
    "Education",
]

_VOCABULARY_LOWER = {t.lower(): t for t in _VOCABULARY}


def normalize_tag(raw: str) -> str | None:
    """Normalize a single tag to the controlled vocabulary.

    Case-insensitive match.  Returns the canonical tag name, or None
    if the tag cannot be mapped to the vocabulary.
    """
    stripped = raw.strip()
    if not stripped:
        return None
    return _VOCABULARY_LOWER.get(stripped.lower())


def normalize_tags(raw_tags: str | list[str] | None) -> list[str]:
    """Normalize a list of tags (or comma-separated string).

    Returns deduplicated canonical tag names.  Unknown tags are
    silently dropped — no new tag rows are created.
    """
    if raw_tags is None:
        return []
    if isinstance(raw_tags, str):
        names = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        names = [t.strip() for t in raw_tags if t and t.strip()]
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        canonical = normalize_tag(name)
        if canonical and canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result
