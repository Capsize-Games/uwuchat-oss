"""Memory context helpers and prompt mode detection."""

from __future__ import annotations

import logging
from typing import List, Optional

from airunner_services.llm.core.tool_registry import ToolCategory

logger = logging.getLogger(__name__)


def _is_omnipotent(owner) -> bool:
    """Return True when the current chatbot has omnipotent knowledge
    enabled and is the system bot."""
    try:
        chatbot = getattr(owner, "chatbot", None)
        if chatbot is None:
            return False
        return bool(
            getattr(chatbot, "is_system_bot", False)
            and getattr(chatbot, "omnipotent_knowledge", False)
        )
    except Exception:
        return False


def get_memory_context(owner, user_query: Optional[str] = None) -> str:
    """Return relevant user memory context when available.

    When the system bot has omnipotent_knowledge enabled, facts from
    all non-blocked chatbots are included instead of only the current
    chatbot's knowledge.
    """
    try:
        from airunner_services.knowledge import get_knowledge_base

        kb = get_knowledge_base()
        omnipotent = _is_omnipotent(owner)
        if user_query:
            if omnipotent:
                context = _search_omnipotent_memory(kb, user_query, owner)
                # Also pull email thread summaries.
                email_context = _search_email_context(user_query)
                if email_context:
                    if context:
                        context += "\n\n" + email_context
                    else:
                        context = email_context
                return context
            return _search_memory_context(kb, user_query)
        if omnipotent:
            return kb.get_omnipotent_context(max_chars=2000)
        return kb.get_context(max_chars=2000)
    except Exception:
        logger.debug("Memory context retrieval failed", exc_info=True)
        return ""


def _search_memory_context(kb, user_query: str) -> str:
    """Return one formatted knowledge block from RAG results."""
    results = kb.search_rag(user_query, k=10)
    if not results:
        return ""
    lines = ["## Relevant Knowledge", ""]
    lines.extend(f"- {result}" for result in results)
    return "\n".join(lines)


def _search_omnipotent_memory(kb, user_query: str, owner=None) -> str:
    """Return one formatted knowledge block from omnipotent RAG results.

    Also attempts entity-aware lookup: if the query contains
    capitalized name-like tokens, resolves them against the entities
    table and pulls entity-scoped facts.
    """
    results = kb.search_omnipotent_rag(user_query, k=10, agent=owner)
    lines: list[str] = []

    if results:
        lines = ["## Relevant Knowledge", ""]
        lines.extend(f"- {result}" for result in results)

    # Entity-aware lookup: scan query for name-like tokens.
    if user_query:
        entity_lines = _search_entity_context(kb, user_query)
        if entity_lines:
            if lines:
                lines.append("")
            lines.extend(entity_lines)

    return "\n".join(lines) if lines else ""


def _search_entity_context(kb, user_query: str) -> list[str]:
    """Return formatted entity-fact lines for name-like tokens in query.

    Quick heuristic: find capitalized 2+-character words, look them up
    via the entity resolver's HMAC blind index, and pull facts about
    each resolved entity.
    """
    import re

    from airunner_services.database.models.entity import Entity
    from airunner_services.database.session import session_scope
    from airunner_services.entity_resolver import _compute_lookup_hash

    tokens = re.findall(r"\b[A-Z][a-z]{1,}\b", user_query or "")
    if not tokens:
        return []

    with session_scope() as session:
        # Cross-chatbot entity lookup — same blocked-chatbot
        # exclusion pattern as kb.search_omnipotent_rag().
        # _is_omnipotent() is already true here (this function is
        # only called from _search_omnipotent_memory), so the
        # system bot should see entities from all non-blocked
        # chatbot scopes.
        blocked = kb._blocked_chatbot_ids()
        lines: list[str] = []
        seen_hashes: set[str] = set()
        for token in tokens:
            lookup_hash = _compute_lookup_hash(token)
            if lookup_hash in seen_hashes:
                continue
            seen_hashes.add(lookup_hash)
            q = session.query(Entity).filter(
                Entity.name_lookup_hash == lookup_hash,
                Entity.deleted.is_(False),
            )
            if blocked:
                q = q.filter(~Entity.chatbot_id.in_(blocked))
            entity = q.first()
            if entity is None:
                continue
            facts = kb.search_entity_facts(entity.id, k=5)
            relationships = kb.get_entity_relationships(entity.id)
            if facts or relationships:
                if not lines:
                    lines.append("## About People")
                lines.append(f"## About {token}")
                lines.extend(f"- {f}" for f in facts)
                lines.extend(relationships)
        return lines


def _search_email_context(user_query: str) -> str:
    """Return formatted email body-chunk excerpts matching *user_query*.

    Only called from the system-bot + omnipotent_knowledge gate.  The
    email-RAG module lives under the active project's package; when
    the active project has none (e.g. headlesscode), no email context
    is injected.
    """
    try:
        import importlib
        import os

        project = os.environ.get("AIRUNNER_PROJECT", "")
        if not project:
            from airunner_services.conf import settings

            project = getattr(settings, "AIRUNNER_PROJECT", "") or ""
        if not project:
            return ""
        mod = importlib.import_module(
            f"projects.{project}.server.email.email_rag"
        )
        results = mod.search_email_body_chunks(user_query, k=8)
        if not results:
            return ""
        lines = ["## Relevant email context", ""]
        lines.extend(f"- {r}" for r in results)
        return "\n".join(lines)
    except Exception:
        return ""


def get_prompt_mode(tool_categories: Optional[List] = None) -> str:
    """Return the prompt mode for the given tool categories."""
    if not tool_categories:
        return "conversational"
    categories = _normalize_tool_categories(tool_categories)
    if ToolCategory.MATH in categories:
        return "math"
    if ToolCategory.ANALYSIS in categories:
        return "precision"
    return "conversational"


def _normalize_tool_categories(tool_categories: List) -> list:
    """Normalize string and enum tool categories to enum values."""
    category_values = []
    for category in tool_categories:
        if isinstance(category, str):
            category_values.extend(
                tool_category
                for tool_category in ToolCategory
                if tool_category.value == category
            )
            continue
        category_values.append(category)
    return category_values
