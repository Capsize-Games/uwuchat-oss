"""Service-owned knowledge base — PostgreSQL + pgvector.

Public API backward-compatible with the original file-based version.
"""

from __future__ import annotations

import threading
from datetime import date
from typing import Optional

from airunner_services.database.models.knowledge_fact import KnowledgeFact
from airunner_services.knowledge_context import (
    get_knowledge_chatbot_id,
    get_knowledge_subject,
)
from airunner_services.knowledge_crud import KnowledgeBaseCrudMixin
from airunner_services.knowledge_helpers import (
    _extract_entities,
    _extract_relationship_words,
    _format_facts_as_markdown,
)
from airunner_services.knowledge_rag import KnowledgeBaseRAGMixin
from airunner_services.knowledge_search import KnowledgeBaseSearchMixin
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application.get_logger import get_logger

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)


class KnowledgeBase(
    KnowledgeBaseCrudMixin,
    KnowledgeBaseSearchMixin,
    KnowledgeBaseRAGMixin,
):
    """Service-owned knowledge base backed by PostgreSQL + pgvector."""

    def __init__(self) -> None:
        self._rag_indexed = False
        self._tfidf_vectorizer = None
        self._tfidf_matrix = None
        self._tfidf_texts: list[str] = []

    # ------------------------------------------------------------------
    # Date helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(date_str: Optional[str]) -> date:
        """Parse a YYYY-MM-DD string, falling back to today."""
        if date_str:
            try:
                return date.fromisoformat(date_str)
            except (ValueError, TypeError):
                pass
        return date.today()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_files(self) -> list[dict[str, object]]:
        """Return distinct knowledge dates with fact counts."""
        from sqlalchemy import func

        rows = (
            KnowledgeFact.objects.query(
                func.date(KnowledgeFact.created_at).label("fact_date"),
                func.count(KnowledgeFact.id),
            )
            .filter(
                KnowledgeFact.deleted.is_(False),
            )
            .group_by(
                func.date(KnowledgeFact.created_at),
            )
            .order_by(
                func.date(KnowledgeFact.created_at).desc(),
            )
            .all()
        )
        return [
            {
                "date": row[0].isoformat() if row[0] else "",
                "count": row[1],
                "size_bytes": int(row[1]) * 80,
            }
            for row in rows
        ]

    def _list_dates(self) -> list[date]:
        """Return distinct dates with facts, newest first."""
        from sqlalchemy import func

        rows = (
            KnowledgeFact.objects.query(
                func.date(KnowledgeFact.created_at).label("fact_date"),
            )
            .filter(
                KnowledgeFact.deleted.is_(False),
            )
            .distinct()
            .order_by(
                func.date(KnowledgeFact.created_at).desc(),
            )
            .scalars()
        )
        return [row for row in rows if row is not None]

    def read_file(self, date_str: Optional[str] = None) -> str:
        """Read knowledge for a specific date as markdown."""
        target = self._parse_date(date_str)
        facts = self._get_facts_for_date(target)
        if not facts:
            return ""
        return _format_facts_as_markdown(facts)

    def read_all(self, max_files: int = 30) -> str:
        """Read facts from the most recent N dates as markdown."""
        dates = self._list_dates()[:max_files]
        if not dates:
            return ""
        all_facts: list[KnowledgeFact] = []
        for d in dates:
            all_facts.extend(self._get_facts_for_date(d))
        if not all_facts:
            return ""
        return _format_facts_as_markdown(all_facts)

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_fact(fact: str) -> str:
        """Strip bullet markers and normalize for comparison."""
        normalized = fact.strip()
        if normalized.startswith(("-", "*", "•")):
            normalized = normalized[1:].strip()
        return normalized.lower()

    def _is_duplicate_fact(self, fact: str) -> bool:
        """Check whether *fact* already exists in this agent's knowledge base."""
        normalized_new = self._normalize_fact(fact)
        chatbot_id = get_knowledge_chatbot_id()
        subject = get_knowledge_subject()
        q = KnowledgeFact.objects.query().filter(
            KnowledgeFact.deleted.is_(False),
            KnowledgeFact.subject == subject,
        )
        if chatbot_id is not None:
            q = q.filter(KnowledgeFact.chatbot_id == chatbot_id)
        existing = q.limit(200).all()
        for row in existing:
            existing_text = row.fact_text
            if not existing_text:
                continue
            normalized_existing = self._normalize_fact(existing_text)
            if (
                normalized_new == normalized_existing
                or normalized_new in normalized_existing
            ):
                return True
            new_entities = _extract_entities(fact)
            existing_entities = _extract_entities(existing_text)
            if not new_entities or not existing_entities:
                continue
            overlap = len(new_entities & existing_entities)
            total = max(len(new_entities), len(existing_entities))
            if overlap / total <= 0.8:
                continue
            new_words = set(normalized_new.split())
            existing_words = set(normalized_existing.split())
            word_overlap = len(
                new_words & existing_words,
            ) / max(len(new_words), len(existing_words))
            if word_overlap > 0.7:
                return True
        return False

    def _find_conflicting_relationship_fact(
        self,
        fact: str,
    ) -> "Optional[KnowledgeFact]":
        """Return an existing fact that conflicts with *fact*.

        A conflict is detected when both the new and existing fact name
        the same person (shared entity) but assign different relationship
        roles (e.g. 'wife' vs 'daughter').  The caller should overwrite
        that row rather than inserting a second contradictory fact.
        """
        new_entities = _extract_entities(fact)
        new_rels = _extract_relationship_words(fact)
        if not new_entities or not new_rels:
            return None

        chatbot_id = get_knowledge_chatbot_id()
        subject = get_knowledge_subject()
        q = KnowledgeFact.objects.query().filter(
            KnowledgeFact.deleted.is_(False),
            KnowledgeFact.subject == subject,
        )
        if chatbot_id is not None:
            q = q.filter(KnowledgeFact.chatbot_id == chatbot_id)
        for row in q.limit(200).all():
            if not row.fact_text:
                continue
            existing_rels = _extract_relationship_words(row.fact_text)
            if not existing_rels:
                continue
            existing_entities = _extract_entities(row.fact_text)
            shared_names = new_entities & existing_entities
            if not shared_names:
                continue
            if existing_rels != new_rels:
                return row
        return None


# Singleton instance
_knowledge_base: Optional[KnowledgeBase] = None
_lock = threading.Lock()


def get_knowledge_base() -> KnowledgeBase:
    """Return the singleton KnowledgeBase instance."""
    global _knowledge_base
    if _knowledge_base is None:
        with _lock:
            if _knowledge_base is None:
                _knowledge_base = KnowledgeBase()
    return _knowledge_base
