"""Add/update write paths for knowledge facts (fail-closed DEK guard).

Both paths call ``self._check_dek_available()`` (defined in
:mod:`airunner_services.knowledge_crud._base`) before mutating the
encrypted ``fact_text`` column.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, UTC
from typing import TYPE_CHECKING, Optional, Tuple

from airunner_services.database.models.knowledge_fact import KnowledgeFact
from airunner_services.knowledge_context import (
    get_knowledge_chatbot_id,
    get_knowledge_subject,
)
from airunner_services.knowledge_crud._base import (
    _link_new_fact_relations,
    _resolve_event_dates,
)
from airunner_services.knowledge_crud._embedding import (
    _compute_fhe_embedding,
)
from airunner_services.knowledge_crud._tags import _normalise_tags

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from airunner_services.knowledge import KnowledgeBase


class KnowledgeBaseWriteMixin:
    """Add and update knowledge facts."""

    def add_fact(
        self: "KnowledgeBase",
        fact: str,
        tags: "str | list[str] | None" = None,
        embedding_model=None,
        section: "str | None" = None,
        date_str: "str | None" = None,
        source_type: str = "user_stated",
        source_url: "str | None" = None,
        confidence: "float | None" = None,
        data_source: "str | None" = None,
        entity_id: "int | None" = None,
        account_id: "int | None" = None,
        tenant_key: "str | None" = None,
    ) -> bool:
        """Record a fact in the knowledge base.

        Args:
            fact: The fact text to store.
            tags: Comma-separated or list of tag names.
            embedding_model: Optional model for computing embedding.
            section: Deprecated — use tags instead.
            date_str: ISO-8601 date string for the fact.
            source_type: One of "user_stated", "inferred",
                "web_search", "conversation_recall".
            source_url: URL of the source (web_search only).
            confidence: 0.0–1.0 or None for "not assessed".
            data_source: Where the signal came from — "conversation",
                "email", "bluesky", "steam", etc.
            account_id: Account ID for cost-tracking and FHE key
                resolution.
            tenant_key: Tenant schema key for cost-tracking resolution.
        """
        self._check_dek_available()

        from airunner_services.utils.application.log_hygiene import (
            summarize_text,
        )

        fact = fact.strip()

        # ---- Sensitive-category filter for inferred facts ----
        from airunner_services.knowledge_filters import (
            filter_inferred_fact,
        )
        blocked, _category = filter_inferred_fact(fact, source_type)
        if blocked:
            return False
        # ---- end filter ----
        resolved_tags = _normalise_tags(tags, section)

        if self._is_duplicate_fact(fact):
            logger.info(
                "Skipping duplicate fact (%s)",
                summarize_text(fact, label="fact"),
            )
            return False

        embedding_enc = _compute_fhe_embedding(
            embedding_model, fact,
            account_id=account_id,
            tenant_key=tenant_key,
        )

        conflict = self._find_conflicting_relationship_fact(fact)
        if conflict is not None:
            with KnowledgeFact.objects.transaction() as tx:
                row = tx.query(KnowledgeFact).get(conflict.id)
                if row is not None:
                    row.fact_text = fact
                    row.updated_at = datetime.now(UTC)
                    if embedding_enc is not None:
                        row.embedding_enc = embedding_enc
            logger.info(
                "Replaced conflicting relationship fact (%s)",
                summarize_text(fact, label="fact"),
            )
            self._rag_indexed = False
            return True

        chatbot_id = get_knowledge_chatbot_id()
        subject = get_knowledge_subject()

        # Resolve event dates for this fact (Part 2 — Stage A+B).
        event_fields = _resolve_event_dates(fact)

        with KnowledgeFact.objects.transaction() as tx:
            row = KnowledgeFact(
                fact_text=fact,
                embedding_enc=embedding_enc,
                chatbot_id=chatbot_id,
                subject=subject,
                source_type=source_type,
                source_url=source_url,
                confidence=confidence,
                data_source=data_source,
                entity_id=entity_id,
                **event_fields,
            )
            tx.add(row)
            tx.flush()
            self._link_fact_tags(
                tx, row, resolved_tags, chatbot_id=chatbot_id
            )

        tag_label = ", ".join(resolved_tags) if resolved_tags else "untagged"
        logger.info(
            "Added fact [%s] (%s)",
            tag_label,
            summarize_text(fact, label="fact"),
        )
        self._rag_indexed = False

        # Link relations to similar existing facts (Part 4).
        _link_new_fact_relations(
            row.id, fact, chatbot_id, embedding_model
        )

        return True

    def update_fact(
        self: "KnowledgeBase",
        old_text: str,
        new_text: str,
        date_str: Optional[str] = None,
        is_regex: bool = False,
    ) -> Tuple[bool, int]:
        """Update facts matching *old_text* to *new_text*."""
        self._check_dek_available()

        with KnowledgeFact.objects.transaction() as tx:
            query = tx.query(KnowledgeFact).filter(
                KnowledgeFact.deleted.is_(False),
            )
            if date_str is not None:
                from sqlalchemy import func

                query = query.filter(
                    func.date(KnowledgeFact.created_at)
                    == self._parse_date(date_str)
                )
            total = 0
            for row in query.all():
                if is_regex:
                    if re.search(old_text, row.fact_text):
                        row.fact_text = re.sub(
                            old_text,
                            new_text,
                            row.fact_text,
                        )
                        row.updated_at = datetime.now(UTC)
                        total += 1
                elif old_text in row.fact_text:
                    row.fact_text = row.fact_text.replace(old_text, new_text)
                    row.updated_at = datetime.now(UTC)
                    total += 1
            if total > 0:
                self._rag_indexed = False
        return total > 0, total
