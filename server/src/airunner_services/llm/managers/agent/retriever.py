"""Retriever helpers backed by the pgvector store."""

from typing import List, Optional, Sequence

from langchain_core.documents import Document

from airunner_services.llm.managers.agent.pgvector_store import PgVectorStore


class DocumentIndexRetriever:
    """Query the pgvector store, optionally scoped to specific documents."""

    def __init__(
        self,
        embedding_model,
        similarity_top_k: int = 5,
        doc_ids: Optional[Sequence[str]] = None,
    ):
        self._embedding_model = embedding_model
        self._similarity_top_k = similarity_top_k
        self._doc_ids = list(doc_ids) if doc_ids else None

    def retrieve(self, query: str) -> List[Document]:
        hits = PgVectorStore.similarity_search(
            query,
            self._embedding_model,
            self._similarity_top_k,
            self._doc_ids,
        )
        return [hit.document for hit in hits]


class MultiIndexRetriever:
    """Search the pgvector store across the user's active documents.

    Only documents marked ``active=True`` in the database are searched
    (plus any transient documents loaded into RAG this session via
    ``load_*_into_rag``).  Users control the active set via the Documents
    panel — there is no automatic filtering.
    """

    def __init__(
        self,
        rag_mixin,
        similarity_top_k: int = 5,
        **kwargs,
    ):
        self._rag_mixin = rag_mixin
        self._similarity_top_k = similarity_top_k

    def retrieve(self, query: str) -> List[Document]:
        embedding_model = getattr(self._rag_mixin, "embedding", None)
        if embedding_model is None:
            return []

        doc_ids = list(self._rag_mixin._get_active_document_ids())
        for doc_id in getattr(self._rag_mixin, "_transient_doc_ids", []):
            if doc_id not in doc_ids:
                doc_ids.append(doc_id)

        if not doc_ids:
            if hasattr(self._rag_mixin, "logger"):
                self._rag_mixin.logger.warning(
                    "No active documents selected. Please activate documents "
                    "in the Documents panel."
                )
            return []

        if hasattr(self._rag_mixin, "logger"):
            self._rag_mixin.logger.info(
                "Searching %d active document(s) in pgvector", len(doc_ids)
            )

        try:
            hits = PgVectorStore.similarity_search(
                query,
                embedding_model,
                self._similarity_top_k,
                doc_ids,
            )
        except Exception as exc:
            if hasattr(self._rag_mixin, "logger"):
                self._rag_mixin.logger.error(
                    "pgvector retrieval failed: %s", exc
                )
            return []

        return [hit.document for hit in hits]
