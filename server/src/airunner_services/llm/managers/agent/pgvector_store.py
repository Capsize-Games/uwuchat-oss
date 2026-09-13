"""PostgreSQL/pgvector-backed vector store for RAG documents.

All operations run inside ``session_scope()`` so they are automatically
scoped to the active tenant schema.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from langchain_core.documents import Document

from airunner_services.database.models.document_chunk import DocumentChunk

QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "


class ScoredDocument:
    """Document search hit with cosine-similarity score (1.0 = identical)."""

    def __init__(self, document: Document, score: float) -> None:
        self.document = document
        self.score = score


def embed_passages(
    embedding_model: Any,
    texts: Sequence[str],
    priority: str = "live",
) -> list[list[float]]:
    """Embed document chunks with the e5 ``passage:`` prefix."""
    prefixed = [f"{PASSAGE_PREFIX}{text}" for text in texts]
    return embedding_model.embed_documents(prefixed, priority=priority)


def embed_query(
    embedding_model: Any,
    text: str,
    priority: str = "live",
) -> list[float]:
    """Embed a search query with the e5 ``query:`` prefix."""
    return embedding_model.embed_query(
        f"{QUERY_PREFIX}{text}", priority=priority,
    )


def embed_texts(
    embedding_model: Any,
    texts: list[str],
    priority: str = "live",
) -> list[list[float]]:
    """Embed a batch of texts without prefix."""
    return embedding_model.embed_documents(texts, priority=priority)


def _with_doc_id(chunk: Any) -> dict:
    """Return a metadata dict that includes the chunk's document ID."""
    meta = dict(chunk.chunk_metadata) if chunk.chunk_metadata else {}
    meta["chunk_id"] = chunk.id
    meta["document_id"] = chunk.doc_id or ""
    return meta


class PgVectorStore:
    """Tenant-scoped vector store over the ``document_chunks`` table."""

    @staticmethod
    def add_document_chunks(
        document_id: Optional[int],
        doc_id: str,
        embedding_model: Any,
        documents: Sequence[Document],
    ) -> int:
        """Embed and persist chunks for one document.

        Existing rows for ``doc_id`` are removed first so re-indexing is
        idempotent.  Returns the number of chunks written.
        """
        texts = [
            doc.page_content for doc in documents if doc.page_content.strip()
        ]
        kept = [doc for doc in documents if doc.page_content.strip()]
        if not texts:
            return 0

        vectors = embed_passages(embedding_model, texts)

        with DocumentChunk.objects.transaction() as tx:
            tx.query(DocumentChunk).filter(
                DocumentChunk.doc_id == doc_id,
            ).delete(synchronize_session=False)

            rows = [
                DocumentChunk(
                    document_id=document_id,
                    doc_id=doc_id,
                    chunk_index=index,
                    content=doc.page_content,
                    chunk_metadata=_json_safe(doc.metadata),
                    embedding=vector,
                )
                for index, (doc, vector) in enumerate(zip(kept, vectors))
            ]
            tx.add_all(rows)

        return len(rows)

    @staticmethod
    def similarity_search_by_vector(
        query_vector: Sequence[float],
        k: int,
        doc_ids: Optional[Sequence[str]] = None,
    ) -> list[ScoredDocument]:
        """Return the ``k`` nearest chunks by cosine distance."""
        if k <= 0:
            return []

        distance = DocumentChunk.embedding.cosine_distance(
            list(query_vector),
        ).label("distance")

        q = DocumentChunk.objects.query(DocumentChunk, distance)
        if doc_ids:
            q = q.filter(DocumentChunk.doc_id.in_(list(doc_ids)))
        rows = q.order_by(distance).limit(k).all()

        return [
            ScoredDocument(
                document=Document(
                    page_content=chunk.content,
                    metadata=_with_doc_id(chunk),
                ),
                score=1.0 - float(dist),
            )
            for chunk, dist in rows
        ]

    @classmethod
    def similarity_search(
        cls,
        query: str,
        embedding_model: Any,
        k: int,
        doc_ids: Optional[Sequence[str]] = None,
    ) -> list[ScoredDocument]:
        """Embed ``query`` and return the ``k`` nearest chunks."""
        query_vector = embed_query(embedding_model, query)
        return cls.similarity_search_by_vector(query_vector, k, doc_ids)

    @staticmethod
    def delete_document(doc_id: str) -> int:
        """Remove all chunks for one document.  Returns rows deleted."""
        return (
            DocumentChunk.objects.query()
            .filter(
                DocumentChunk.doc_id == doc_id,
            )
            .delete(synchronize_session=False)
        )

    @staticmethod
    def document_chunk_count(doc_id: str) -> int:
        """Return the number of stored chunks for one document."""
        return (
            DocumentChunk.objects.query()
            .filter(
                DocumentChunk.doc_id == doc_id,
            )
            .count()
        )


def _json_safe(metadata: Optional[dict]) -> dict:
    """Return a JSON-serializable copy of chunk metadata."""
    if not metadata:
        return {}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        try:
            import json

            json.dumps(value)
            safe[key] = value
        except (TypeError, ValueError):
            safe[key] = str(value)
    return safe
