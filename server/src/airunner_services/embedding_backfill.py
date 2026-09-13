"""Backfill embeddings for KnowledgeFact and ConversationTurn rows.

Provides idempotent, batched backfill functions that pick up rows
with ``embedding_enc IS NULL`` and embed them.  Safe to re-run.

See ``plans/uwuchat-temporal-fact-lifecycle-and-rag-indexing-fix.md``
Part 5 for design rationale.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def backfill_fact_embeddings(
    embedding_model,
    batch_size: int = 50,
    chatbot_id: Optional[int] = None,
) -> dict:
    """Embed KnowledgeFact rows with NULL embedding_enc.

    Delegates to ``KnowledgeBase.index_all_facts`` for the actual
    embedding logic (FHE encryption, normalization, etc.).

    Returns dict with ``total_embedded`` count.
    """
    from airunner_services.knowledge import get_knowledge_base

    kb = get_knowledge_base()
    total = kb.index_all_facts(embedding_model, batch_size=batch_size)
    return {"total_embedded": total}


def backfill_turn_embeddings(
    embedding_model,
    batch_size: int = 50,
    chatbot_id: Optional[int] = None,
) -> dict:
    """Embed ConversationTurn rows with NULL embedding_enc.

    Returns dict with ``total_embedded`` and ``errors`` counts.
    """
    from airunner_services.database.models.conversation_turn import (
        ConversationTurn,
    )
    from airunner_services.database.session import session_scope
    from airunner_services.llm.managers.agent.pgvector_store import (
        embed_texts,
    )
    from airunner_services.knowledge_crud import (
        _get_or_create_public_context,
    )
    from airunner_services.utils.crypto.fhe_helpers import (
        encrypt_embedding,
        l2_normalize,
    )
    from airunner_services.data.tenant import get_account_id

    account_id = get_account_id()
    if account_id is None:
        logger.warning("No account_id — skipping turn backfill")
        return {"total_embedded": 0, "errors": 0}

    try:
        public_ctx = _get_or_create_public_context(account_id)
    except Exception as exc:
        logger.warning("Cannot get FHE context: %s", exc)
        return {"total_embedded": 0, "errors": 0}

    total_embedded = 0
    errors = 0
    last_id = 0

    while True:
        with session_scope() as session:
            batch = (
                session.query(ConversationTurn)
                .filter(
                    ConversationTurn.id > last_id,
                    ConversationTurn.embedding_enc.is_(None),
                    ConversationTurn.deleted.is_(False),
                )
                .order_by(ConversationTurn.id)
                .limit(batch_size)
                .all()
            )

            if not batch:
                break

            last_id = max(t.id for t in batch)
            texts = [t.content for t in batch]

            try:
                vectors = embed_texts(
                    embedding_model, texts, priority="bulk",
                )
            except Exception as exc:
                logger.warning("Embedding batch failed: %s", exc)
                errors += len(batch)
                continue

            for turn, vector in zip(batch, vectors):
                try:
                    normalized = l2_normalize(vector)
                    encrypted = encrypt_embedding(
                        normalized, public_ctx
                    )
                    turn.embedding_enc = encrypted
                    total_embedded += 1
                except Exception as exc:
                    logger.warning(
                        "Failed to embed turn %d: %s", turn.id, exc
                    )
                    errors += 1

            session.flush()

    return {"total_embedded": total_embedded, "errors": errors}


def compute_turn_embedding(content: str):
    """Compute and FHE-encrypt an embedding for one conversation turn.

    Returns the serialized ciphertext bytes or None if the embedding
    model or FHE key material is unavailable.  Failures are logged at
    WARNING with the error class so they are distinguishable from
    "not yet processed" (still-NULL because the backfill hasn't
    reached this row yet).
    """
    try:
        from projects.uwuchat.server.embedding_provider import (
            get_embedding_provider,
        )
        from airunner_services.llm.managers.agent.pgvector_store import (
            embed_texts,
        )
        from airunner_services.utils.crypto.fhe_helpers import (
            encrypt_embedding,
            l2_normalize,
        )
        from airunner_services.data.tenant import get_account_id
        from airunner_services.knowledge_crud import (
            _get_or_create_public_context,
        )

        provider = get_embedding_provider()
        vectors = embed_texts(provider, [content], priority="bulk")
        if not vectors or vectors[0] is None:
            return None

        account_id = get_account_id()
        if account_id is None:
            return None

        public_ctx = _get_or_create_public_context(account_id)
        normalized = l2_normalize(vectors[0])
        return encrypt_embedding(normalized, public_ctx)
    except Exception as exc:
        logger.warning(
            "FHE turn embedding failed (class=%s): %s",
            type(exc).__name__,
            exc,
        )
        return None
