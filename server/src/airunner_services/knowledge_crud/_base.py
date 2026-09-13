"""Fail-closed DEK guard and shared helpers for knowledge-fact writes.

The guard in :class:`KnowledgeBaseCrudBase` is the single choke point
every KnowledgeFact write path must pass before mutating the encrypted
``fact_text`` column.  Without an active per-user DEK the write raises
``DataEncryptionError`` instead of silently falling back to the global
keyring or plaintext, which would defeat per-user envelope encryption.

This module also hosts the write-path helpers shared by
:mod:`airunner_services.knowledge_crud._write`: Stage A+B date
resolution (:func:`_resolve_event_dates`) and best-effort relation
linking (:func:`_link_new_fact_relations`).
"""

from __future__ import annotations

import logging
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer

from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError,
)
from airunner_services.utils.crypto.dek_cache import get_user_dek

logger = logging.getLogger(__name__)


class KnowledgeBaseCrudBase:
    """Fail-closed DEK guard shared by all knowledge-fact writes."""

    _tfidf_vectorizer: Optional[TfidfVectorizer]
    _tfidf_matrix = None
    _tfidf_texts: list[str]
    _rag_indexed: bool

    def _check_dek_available(self) -> None:
        """Check that a per-user DEK is available for encrypted writes.

        Raises :class:`DataEncryptionError` when no DEK is in context.
        This guard prevents silent fallback to the global keyring or
        plaintext, which would defeat per-user envelope encryption.

        Callers must wrap their operations in ``task_dek_scope()``
        (see :mod:`airunner_services.tasks.task_helpers`) to ensure
        a DEK relay entry is active.
        """
        dek = get_user_dek()
        if dek is None:
            raise DataEncryptionError(
                "KnowledgeFact write requires an active DEK. "
                "The caller must be wrapped in task_dek_scope() "
                "to ensure per-user envelope encryption for fact_text. "
                "This guard prevents silent fallback to the global "
                "keyring or plaintext, which would compromise data "
                "confidentiality."
            )


def _link_new_fact_relations(
    fact_id: int,
    fact_text: str,
    chatbot_id: int | None,
    embedding_model,
) -> None:
    """Link a newly-recorded fact to related existing facts.

    Uses the similarity-search and heuristic classifier from
    ``fact_relation_linker``.  Never raises — relation linking is
    best-effort.
    """
    if chatbot_id is None:
        return
    try:
        from airunner_services.fact_relation_linker import (
            link_fact_relations,
        )

        link_fact_relations(
            fact_id, fact_text, chatbot_id, embedding_model
        )
    except Exception:
        logger.debug(
            "Relation linking skipped for fact %d", fact_id,
            exc_info=True,
        )


def _resolve_event_dates(fact: str) -> dict:
    """Run Stage A+B date resolution for a fact being recorded.

    Returns a dict of KnowledgeFact column values to pass as kwargs
    on creation.  When resolution fails or the fact has no date,
    returns an empty dict (columns stay at their defaults).
    """
    try:
        from airunner_services.fact_date_extractor import (
            resolve_fact_dates,
        )

        result = resolve_fact_dates(fact)
        if result is None:
            return {}

        return {
            "event_date": result.get("event_date"),
            "event_end_date": result.get("event_end_date"),
            "event_time": result.get("event_time"),
            "recurring": result.get("recurring", False),
            "temporal_status": result.get("temporal_status", "durable"),
        }
    except Exception:
        logger.debug(
            "Date resolution skipped for fact", exc_info=True
        )
        return {}
