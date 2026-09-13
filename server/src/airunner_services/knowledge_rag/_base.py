"""Core RAG mixin — composes TF-IDF, FHE, and helper method groups."""

from __future__ import annotations

import logging

from airunner_services.database.models.knowledge_fact import KnowledgeFact
from airunner_services.knowledge_rag._fhe import KnowledgeBaseFHEMixin
from airunner_services.knowledge_rag._helpers import (
    KnowledgeBaseHelpersMixin,
)
from airunner_services.knowledge_rag._tfidf import (
    KnowledgeBaseTFIDFMixin,
)

logger = logging.getLogger(__name__)


class KnowledgeBaseRAGMixin(
    KnowledgeBaseTFIDFMixin,
    KnowledgeBaseFHEMixin,
    KnowledgeBaseHelpersMixin,
):
    """RAG and embeddings methods."""

    _rag_indexed: bool

    def _get_unindexed_facts(
        self: "KnowledgeBase",
    ) -> list[KnowledgeFact]:
        """Return facts whose encrypted embedding is NULL."""
        return (
            KnowledgeFact.objects.query()
            .filter(
                KnowledgeFact.embedding_enc.is_(None),
                KnowledgeFact.deleted.is_(False),
            )
            .all()
        )

    def index_all_facts(
        self: "KnowledgeBase",
        embedding_model,
        batch_size: int = 100,
    ) -> int:
        """Generate, encrypt, and store embeddings for all unindexed facts.

        *embedding_model* must be a LangChain-compatible embedding
        object (e.g. the one stored as ``agent.embedding``).

        Each embedding is L2-normalized and encrypted with the
        account's FHE public context before storage.  The plaintext
        vector never touches the database.

        Requires an active DEK and FHE key material for the current
        account — fails with a warning and skips if unavailable.
        """
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

        unindexed = self._get_unindexed_facts()
        if not unindexed:
            return 0

        account_id = get_account_id()
        if account_id is None:
            logger.warning(
                "index_all_facts: no account_id in context; skipping"
            )
            return 0

        try:
            public_ctx = _get_or_create_public_context(account_id)
        except Exception as exc:
            logger.warning(
                "index_all_facts: cannot get FHE public context "
                "for account %d: %s; skipping",
                account_id, exc,
            )
            return 0

        total = 0
        for i in range(0, len(unindexed), batch_size):
            batch = unindexed[i : i + batch_size]
            texts = [f.fact_text for f in batch]
            vectors = embed_texts(embedding_model, texts)
            with KnowledgeFact.objects.transaction() as tx:
                for j, fact in enumerate(batch):
                    normalized = l2_normalize(vectors[j])
                    encrypted = encrypt_embedding(
                        normalized, public_ctx,
                    )
                    tx.query(KnowledgeFact).filter(
                        KnowledgeFact.id == fact.id,
                    ).update(
                        {"embedding_enc": encrypted},
                        synchronize_session=False,
                    )
            total += len(batch)
        self._rag_indexed = True
        return total
