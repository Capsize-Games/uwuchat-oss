"""Service-owned vector store for RAG document chunks (pgvector-backed)."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from airunner_services.database.base import BaseModel

# Embedding dimension for the active embedding model (intfloat/e5-large).
EMBEDDING_DIM = 1024


class DocumentChunk(BaseModel):
    """One embedded chunk of a knowledge-base document.

    Replaces the legacy on-disk numpy index.  Embeddings live in
    PostgreSQL via the ``vector`` extension so retrieval is a single
    tenant-scoped SQL query instead of brute-force numpy similarity.
    """

    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # FK to the document registry row this chunk was extracted from.
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Stable per-document hash id used by retrievers to filter active docs.
    doc_id = Column(String, nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=False)
    chunk_metadata = Column(JSONB, nullable=True)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=False)


__all__ = ["DocumentChunk", "EMBEDDING_DIM"]
