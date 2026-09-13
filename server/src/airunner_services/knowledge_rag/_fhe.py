"""FHE-encrypted vector similarity search methods."""

from __future__ import annotations

import logging

from airunner_services.database.models.knowledge_fact import KnowledgeFact
from airunner_services.utils.crypto.fhe_search import (
    FHE_CANDIDATE_CAP,
)

logger = logging.getLogger(__name__)


class KnowledgeBaseFHEMixin:
    """Homomorphically-encrypted embedding similarity search."""

    def _fhe_score_candidates(
        self,
        candidates: list[KnowledgeFact],
        normalized_query: "list[float]",
        account_id: int,
    ) -> list[tuple[KnowledgeFact, float]]:
        """Score *candidates* via FHE dot-product with *normalized_query*.

        Delegates to the shared ``fhe_similarity_rank`` helper.
        """
        from airunner_services.utils.crypto.fhe_search import (
            fhe_similarity_rank,
        )

        return fhe_similarity_rank(
            candidates,
            get_ciphertext=lambda f: f.embedding_enc,
            account_id=account_id,
            normalized_query=normalized_query,
            top_k=len(candidates),
        )

    def _similarity_search_omnipotent(
        self: "KnowledgeBase",
        query_text: str,
        k: int = 5,
        embedding_model=None,
    ) -> list[KnowledgeFact]:
        """FHE vector similarity search across all non-blocked chatbots.

        Replaces the former pgvector ``cosine_distance`` query with
        homomorphically encrypted dot products computed client-side
        (in the server process, not in SQL).

        Steps:
            1. Compute and L2-normalize the query vector.
            2. Pre-filter candidates in SQL (plaintext columns only).
            3. Cap at ``FHE_CANDIDATE_CAP``, ordered by recency.
            4. Score each candidate via FHE dot-product.
            5. Return top-k by score.
        """
        if k <= 0 or embedding_model is None:
            return []

        from airunner_services.llm.managers.agent.pgvector_store import (
            embed_query,
        )
        from airunner_services.utils.crypto.fhe_helpers import (
            l2_normalize,
        )
        from airunner_services.data.tenant import get_account_id

        account_id = get_account_id()
        if account_id is None:
            logger.warning(
                "No account_id in tenant context — "
                "skipping FHE search"
            )
            return []

        query_vector = embed_query(embedding_model, query_text)
        normalized_query = l2_normalize(query_vector)

        # Pre-filter in SQL — only non-sensitive plaintext columns.
        blocked = self._blocked_chatbot_ids()
        q = KnowledgeFact.objects.query().filter(
            KnowledgeFact.deleted.is_(False),
            KnowledgeFact.fact_text != "",
            KnowledgeFact.embedding_enc.isnot(None),
        )
        if blocked:
            q = q.filter(~KnowledgeFact.chatbot_id.in_(blocked))

        candidates = (
            q.order_by(KnowledgeFact.created_at.desc())
            .limit(FHE_CANDIDATE_CAP)
            .all()
        )

        if not candidates:
            return []

        scored = self._fhe_score_candidates(
            candidates,
            normalized_query.tolist(),
            account_id,
        )
        return [fact for fact, _score in scored[:k]]

    def similarity_search(
        self: "KnowledgeBase",
        query_text: str,
        k: int = 5,
        embedding_model=None,
    ) -> list[KnowledgeFact]:
        """Return the ``k`` most-similar facts by FHE cosine similarity.

        Replaces the former pgvector ``cosine_distance`` query with
        homomorphically encrypted dot products.
        """
        if k <= 0 or embedding_model is None:
            return []

        from airunner_services.llm.managers.agent.pgvector_store import (
            embed_query,
        )
        from airunner_services.utils.crypto.fhe_helpers import (
            l2_normalize,
        )
        from airunner_services.data.tenant import get_account_id
        from airunner_services.knowledge_context import (
            get_knowledge_chatbot_id,
        )

        account_id = get_account_id()
        if account_id is None:
            logger.warning(
                "No account_id in tenant context — "
                "skipping FHE search"
            )
            return []

        query_vector = embed_query(embedding_model, query_text)
        normalized_query = l2_normalize(query_vector)

        chatbot_id = get_knowledge_chatbot_id()
        q = KnowledgeFact.objects.query().filter(
            KnowledgeFact.deleted.is_(False),
            KnowledgeFact.embedding_enc.isnot(None),
        )
        if chatbot_id is not None:
            q = q.filter(KnowledgeFact.chatbot_id == chatbot_id)

        candidates = (
            q.order_by(KnowledgeFact.created_at.desc())
            .limit(FHE_CANDIDATE_CAP)
            .all()
        )

        if not candidates:
            return []

        scored = self._fhe_score_candidates(
            candidates,
            normalized_query.tolist(),
            account_id,
        )
        return [fact for fact, _score in scored[:k]]
