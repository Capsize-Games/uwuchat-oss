"""
Recall knowledge tool.

Searches the knowledge base using semantic (RAG), keyword,
and TF-IDF backends.
"""

from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import tool, ToolCategory
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

from ._helpers import merge_search_results

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)


def _is_omnipotent() -> bool:
    """Return True when the current chatbot is the system bot with
    omnipotent_knowledge enabled."""
    try:
        from airunner_services.database.models.chatbot import Chatbot
        from airunner_services.knowledge_context import (
            get_knowledge_chatbot_id,
        )

        chatbot_id = get_knowledge_chatbot_id()
        if chatbot_id is None:
            return False
        chatbot = Chatbot.objects.get(chatbot_id)
        if chatbot is None:
            return False
        return bool(
            getattr(chatbot, "is_system_bot", False)
            and getattr(chatbot, "omnipotent_knowledge", False)
        )
    except Exception:
        return False


@tool(
    name="recall_knowledge",
    category=ToolCategory.KNOWLEDGE,
    description=(
        "Look up stored personal facts about THIS SPECIFIC USER or THIS "
        "CHARACTER'S established backstory. REQUIRED before stating any "
        "specific fact about a named person. "
        "Use the optional 'tag' parameter to narrow results to a "
        "specific category (Identity, Health, Work, Relationships, "
        "Goals, Preferences, Hobbies, Education) — e.g. when the "
        "user asks broadly 'what do you know about my work situation'."
    ),
    return_direct=False,
    requires_api=False,
    defer_loading=False,
    keywords=[
        "remember",
        "memory",
        "recall",
        "what do I know about",
    ],
    input_examples=[
        {"query": "user's health conditions"},
        {"query": "what projects is the user working on"},
        {"query": "user's name and location"},
        {"query": "user's hobbies and interests"},
    ],
)
def recall_knowledge(
    query: Annotated[str, "What you're trying to remember or find"],
    tag: Annotated[
        str,
        "Optional category filter: Identity, Health, Work, "
        "Relationships, Goals, Preferences, Hobbies, Education",
    ] = "",
    max_results: Annotated[int, "Maximum facts to return"] = 5,
    entity_name: Annotated[
        str,
        "When searching for facts about a specific named person or "
        "entity, provide their name for resolution",
    ] = "",
    entity_type: Annotated[
        str,
        "Type of the entity: person, place, thing, concept, "
        "organization, or event.  Only used when entity_name is also "
        "provided.",
    ] = "person",
    api: Any = None,
) -> str:
    """Search the knowledge base for relevant facts.

    Uses semantic search to find facts matching the query across all
    stored knowledge files.  When the system bot has
    omnipotent_knowledge enabled, facts from ALL non-blocked chatbots
    are searched instead of only the current chatbot's knowledge.

    If *entity_name* is provided, facts about that resolved entity
    are included in addition to normal chatbot-scoped facts.
    """
    try:
        from airunner_services.knowledge import get_knowledge_base
        from airunner_services.knowledge_context import (
            get_knowledge_chatbot_id,
        )
        from airunner_services.entity_resolver import (
            _compute_lookup_hash,
            normalize_entity_type,
        )
        from airunner_services.database.models.entity import Entity
        from airunner_services.database.session import session_scope

        kb = get_knowledge_base()

        # Resolve entity if query targets a named entity.
        # Uses a lookup-only path — never creates a new entity as a
        # side effect of asking "what do I know about X?".
        resolved_entity_id: int | None = None
        if entity_name and entity_name.strip():
            chatbot_id = get_knowledge_chatbot_id()
            if chatbot_id is not None:
                lookup_hash = _compute_lookup_hash(entity_name.strip())
                et = normalize_entity_type(entity_type)
                with session_scope() as session:
                    existing = (
                        session.query(Entity)
                        .filter(
                            Entity.chatbot_id == chatbot_id,
                            Entity.name_lookup_hash == lookup_hash,
                            Entity.entity_type == et,
                            Entity.deleted.is_(False),
                        )
                        .first()
                    )
                    if existing is not None:
                        resolved_entity_id = existing.id

        # Normalize tag to controlled vocabulary.
        resolved_tag = ""
        if tag and tag.strip():
            from airunner_services.tag_vocabulary import normalize_tag

            resolved = normalize_tag(tag.strip())
            resolved_tag = resolved or ""

        omnipotent = _is_omnipotent()
        logger.info(
            "[RECALL] omnipotent=%s query=%r max_results=%s",
            omnipotent, query, max_results,
        )
        if omnipotent:
            rag_results = kb.search_omnipotent_rag(
                query, k=max_results, agent=api,
            )
            logger.info(
                "[RECALL] omnipotent RAG results: %s", len(rag_results),
            )
            facts = kb._search_facts_omnipotent(
                query, limit=max_results,
            )
            logger.info(
                "[RECALL] omnipotent keyword facts: %s", len(facts),
            )
            keyword_results = _format_fact_rows(facts)
        else:
            agent = api if api and hasattr(api, "search") else None
            rag_results = kb.search_rag(
                query, k=max_results, agent=agent,
            )
            if resolved_tag:
                tag_facts = kb._get_facts_for_tag(resolved_tag)
                keyword_results = _format_fact_rows(
                    tag_facts[:max_results]
                )
            else:
                keyword_results = kb.search(
                    query, max_results=max_results,
                )
            logger.info(
                "[RECALL] scoped RAG: %s keyword: %s",
                len(rag_results), len(keyword_results),
            )

        results = merge_search_results(rag_results, keyword_results, [])

        # Append entity-scoped facts if a named entity was resolved.
        if resolved_entity_id is not None:
            entity_facts = kb.search_entity_facts(
                resolved_entity_id, k=max_results,
            )
            if entity_facts:
                if not results:
                    results = []
                results.extend(entity_facts)

        # Append related facts (Part 4) for facts that have links.
        _fact_rows = facts if omnipotent else (
            tag_facts if resolved_tag else None
        )
        if _fact_rows:
            related = _append_related_facts(_fact_rows[:3])
            if related:
                results = list(results) + related

        if not results:
            return f"No knowledge found for: '{query}'."

        return "\n".join(f"- {fact}" for fact in results[:max_results])

    except Exception as e:
        logger.error(f"Error recalling knowledge: {e}")
        return f"Error: {str(e)}"


def _append_related_facts(facts: list) -> list[str]:
    """Return related-fact lines for the given facts."""
    from airunner_services.fact_relation_linker import (
        get_related_facts,
    )

    lines = []
    seen = set()
    for f in facts:
        fid = getattr(f, "id", None)
        if fid is None:
            continue
        for rel in get_related_facts(fid, limit=3):
            key = (fid, rel["fact_id"])
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                f"[related: {rel['relation_type']}]"
                f" {rel['fact_text']}"
            )
    return lines


def _format_fact_rows(facts: list) -> list[dict[str, str]]:
    """Format KnowledgeFact rows as dicts with 'line', 'timestamp',
    and optional 'source_type' / 'confidence' keys."""
    from datetime import datetime

    facts_sorted = sorted(
        facts,
        key=lambda f: f.created_at or datetime.min,
        reverse=True,
    )
    result: list[dict[str, str]] = []
    for f in facts_sorted:
        if not f.fact_text:
            continue
        ts = ""
        if f.created_at:
            ts = f.created_at.strftime("%Y-%m-%d %H:%M:%S")
        entry: dict[str, str] = {"line": f.fact_text, "timestamp": ts}
        st = getattr(f, "source_type", None)
        if st and st != "user_stated":
            entry["source_type"] = st
        conf = getattr(f, "confidence", None)
        if conf is not None:
            entry["confidence"] = f"{conf:.2f}"
        result.append(entry)
    return result
