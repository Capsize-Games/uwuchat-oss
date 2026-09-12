"""Link newly-recorded KnowledgeFacts to related existing facts.

Uses the existing similarity-search machinery then a cheap LLM
classifier (TOOL_CLASSIFICATION tier) to decide the relation type.
"""
from __future__ import annotations

import datetime
import logging

logger = logging.getLogger(__name__)


def link_fact_relations(
    fact_id: int,
    fact_text: str,
    chatbot_id: int,
    embedding_model=None,
    top_k: int = 5,
) -> int:
    """Find and link related facts for a newly-recorded fact.

    Returns number of relation rows created.
    """
    if embedding_model is None:
        return 0
    try:
        from airunner_services.database.models.knowledge_fact_relation import (
            KnowledgeFactRelation,
        )
        from airunner_services.knowledge import get_knowledge_base

        kb = get_knowledge_base()
        candidates = _similar_facts(
            kb, fact_text, chatbot_id, embedding_model, top_k * 2
        )
        candidates = [f for f in candidates if f.id != fact_id]
        if not candidates:
            return 0

        count = 0
        for candidate in candidates[:top_k]:
            rel_type = _classify_relation(fact_text, candidate)
            if rel_type is None:
                continue

            with KnowledgeFactRelation.objects.transaction() as tx:
                if (
                    tx.query(KnowledgeFactRelation)
                    .filter(
                        KnowledgeFactRelation.fact_id == fact_id,
                        KnowledgeFactRelation.related_fact_id
                        == candidate.id,
                        KnowledgeFactRelation.relation_type
                        == rel_type,
                    )
                    .first()
                    is not None
                ):
                    continue
                now = datetime.datetime.now(datetime.UTC)
                tx.add(
                    KnowledgeFactRelation(
                        fact_id=fact_id,
                        related_fact_id=candidate.id,
                        relation_type=rel_type,
                        created_at=now,
                        updated_at=now,
                    )
                )
                count += 1
        return count
    except Exception:
        logger.warning(
            "link_fact_relations failed for fact %d", fact_id,
            exc_info=True,
        )
        return 0


def _similar_facts(
    kb,
    fact_text: str,
    chatbot_id: int,
    embedding_model,
    limit: int,
) -> list:
    """Find similar facts scoped to the same chatbot."""
    try:
        results = kb.similarity_search(
            fact_text, k=limit, embedding_model=embedding_model
        )
        return [f for f in results if f.chatbot_id == chatbot_id]
    except Exception:
        return []


def _classify_relation(
    new_text: str,
    candidate,
) -> str | None:
    """LLM classifier: unrelated / related / follow_up / supersedes."""
    try:
        cand_text = str(candidate.fact_text or "").strip()
    except Exception:
        return None
    if not cand_text:
        return None

    prompt = (
        "Classify the relationship between two facts about the same"
        " person.\n\n"
        f"New fact: {new_text}\n"
        f"Existing fact: {cand_text}\n\n"
        "Categories:\n"
        "- supersedes — the new fact updates or replaces the old one\n"
        "- follow_up — the new fact is a continuation\n"
        "- related — same topic but neither supersedes nor follows up\n"
        "- unrelated — different topics\n\n"
        "Respond with exactly one word."
    )

    try:
        from airunner_services.fact_date_llm import (
            call_classification_llm,
        )
        result = call_classification_llm(prompt).strip().lower()
    except Exception:
        return None

    valid = {"supersedes", "follow_up", "related", "unrelated"}
    if result in valid:
        return None if result == "unrelated" else result
    first = result.split()[0] if result else ""
    if first in valid:
        return None if first == "unrelated" else first
    return None


def get_related_facts(fact_id: int, limit: int = 3) -> list[dict]:
    """Return directly-linked related facts ordered by recency."""
    try:
        from airunner_services.database.models.knowledge_fact_relation import (
            KnowledgeFactRelation,
        )
        from airunner_services.database.models.knowledge_fact import (
            KnowledgeFact,
        )

        relations = (
            KnowledgeFactRelation.objects.query()
            .filter(
                KnowledgeFactRelation.fact_id == fact_id,
                KnowledgeFactRelation.deleted.is_(False),
            )
            .order_by(KnowledgeFactRelation.created_at.desc())
            .limit(limit)
            .all()
        )

        result = []
        for rel in relations:
            try:
                related = KnowledgeFact.objects.get(
                    rel.related_fact_id
                )
                if related is None:
                    continue
                text = str(related.fact_text or "").strip()
                if not text:
                    continue
                result.append(
                    {
                        "fact_id": related.id,
                        "fact_text": text,
                        "relation_type": rel.relation_type,
                    }
                )
            except Exception:
                continue
        return result
    except Exception:
        return []
