"""TF-IDF keyword search methods with FHE-first fallback."""

from __future__ import annotations

import logging

from airunner_services.database.models.knowledge_fact import KnowledgeFact

logger = logging.getLogger(__name__)


class KnowledgeBaseTFIDFMixin:
    """Keyword search methods — vector-first with TF-IDF fallback."""

    def search_rag(
        self: "KnowledgeBase",
        query: str,
        k: int = 5,
        agent=None,
    ) -> list[str]:
        """Semantic search using FHE-encrypted embeddings.

        Falls back to TF-IDF keyword search when no embedding model
        can be resolved from *agent* or when FHE search returns no
        results (e.g. all candidates have NULL embedding_enc).
        Returns plain fact strings so the result can be consumed
        directly by ``merge_search_results``.
        """
        embedding_model = None
        if agent is not None:
            embedding_model = getattr(agent, "embedding", None)

        if embedding_model is not None:
            facts = self.similarity_search(
                query, k=k, embedding_model=embedding_model
            )
            if facts:
                return [f.fact_text for f in facts if f.fact_text]
            # Vector search returned nothing (e.g. facts have NULL
            # embeddings) — fall through to keyword search.

        # Keyword + TF-IDF fallback
        facts = self.search_facts(query, limit=k)
        return [f.fact_text for f in facts if f.fact_text]

    def search_omnipotent_rag(
        self: "KnowledgeBase",
        query: str,
        k: int = 10,
        agent=None,
    ) -> list[str]:
        """Semantic search across ALL non-blocked chatbots' facts.

        Used by the system bot when omnipotent_knowledge is enabled.
        Tries vector search first (when an embedding model is
        available), then falls back to TF-IDF keyword search.
        """
        embedding_model = None
        if agent is not None:
            embedding_model = getattr(agent, "embedding", None)

        if embedding_model is not None:
            facts = self._similarity_search_omnipotent(
                query, k=k, embedding_model=embedding_model,
            )
            if facts:
                return [f.fact_text for f in facts if f.fact_text]
            # Vector search returned nothing — fall through.

        # TF-IDF keyword fallback
        facts = self._search_facts_omnipotent(query, limit=k)
        return [f.fact_text for f in facts if f.fact_text]

    def _search_facts_omnipotent(
        self: "KnowledgeBase",
        query: str,
        limit: int = 20,
    ) -> list[KnowledgeFact]:
        """TF-IDF search across facts from all non-blocked chatbots.

        fact_text is encrypted with UserEncryptedText — ILIKE cannot
        match ciphertext.  All searches go through in-memory TF-IDF
        over the decrypted candidate set.
        """
        all_facts = self.get_omnipotent_facts(
            limit=min(limit * 40, 500),
        )
        if not all_facts:
            return []
        return self._tfidf_rank(all_facts, query, limit, min_score=0.1)
