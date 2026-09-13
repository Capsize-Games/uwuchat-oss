"""Module-level helpers and constants for the knowledge base."""

from __future__ import annotations

import os
import re
import threading
from datetime import date
from typing import Dict

from airunner_services.database.models.knowledge_fact import KnowledgeFact

ENTITIES_CACHE: Dict[str, str] = {}
ENTITIES_LOCK = threading.Lock()


def _resolved_path_settings_base() -> str:
    """Return the configured base_path or fall back to ~/.local/share/..."""
    from airunner_services.database.models.path_settings import (
        PathSettings,
    )

    try:
        ps = PathSettings.objects.query().first()
        if ps and ps.base_path:
            return str(ps.base_path)
    except Exception:
        pass
    return os.path.expanduser(os.path.join("~", ".local", "share", "airunner"))


def _extract_entities(text: str) -> set[str]:
    """Extract lightweight entity-like tokens (proper nouns, acronyms)."""
    import string

    words = re.findall(r"\b[A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,})*", text)
    words += re.findall(r"\b[A-Z]{2,}\b", text)
    cleaned = set()
    for w in words:
        w = w.strip(string.punctuation + string.whitespace)
        if len(w) >= 3:
            cleaned.add(w)
    return cleaned


_RELATIONSHIP_WORDS: frozenset[str] = frozenset(
    {
        "wife", "husband", "daughter", "son", "mother", "father",
        "sister", "brother", "girlfriend", "boyfriend", "partner",
        "spouse", "mom", "dad", "aunt", "uncle", "niece", "nephew",
        "grandma", "grandpa", "grandmother", "grandfather",
        "boss", "manager", "colleague", "coworker", "fiancée",
        "fiance", "ex", "stepdaughter", "stepson", "stepmom",
        "stepdad",
    }
)


def _extract_relationship_words(text: str) -> frozenset[str]:
    """Return relationship words present in *text*."""
    lower_words = set(re.findall(r"\b[a-z]+\b", text.lower()))
    return frozenset(lower_words & _RELATIONSHIP_WORDS)


def _resolve_section(raw: str) -> str:
    """Return the tag as-is, falling back to 'Notes' when blank."""
    cleaned = raw.strip() if raw else ""
    return cleaned or "Notes"


def _format_facts_as_markdown(facts: list[KnowledgeFact]) -> str:
    """Format a list of facts as a date-grouped markdown string.

    Each fact includes its timestamp in ``[YYYY-MM-DD HH:MM:SS]``
    format so the LLM can see exactly when it was recorded.
    """
    if not facts:
        return ""

    groups: dict[date, list[str]] = {}
    for f_obj in facts:
        dt = f_obj.created_at
        d = dt.date() if dt is not None else date.today()
        ts = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""
        line = f"[{ts}] {f_obj.fact_text}" if ts else f_obj.fact_text
        if d not in groups:
            groups[d] = []
        groups[d].append(line)

    lines: list[str] = []
    for d in sorted(groups.keys(), reverse=True):
        lines.append(f"## {d.isoformat()}")
        for fact in groups[d]:
            lines.append(f"- {fact}")
        lines.append("")
    return "\n".join(lines).strip()
