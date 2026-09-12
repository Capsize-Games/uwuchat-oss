"""DB-backed tests for the pgvector RAG store.

Verifies that chunks are persisted to PostgreSQL and that cosine
similarity search returns them in the correct order.  Requires a
Postgres instance with the ``vector`` extension (the migration installs
it); skips automatically when no test database is reachable.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from airunner_services.database.session import reset_engine, session_scope
from airunner_services.database.models.document_chunk import (
    DocumentChunk,
    EMBEDDING_DIM,
)
from airunner_services.database.setup_database import setup_database
from airunner_services.llm.managers.agent.pgvector_store import PgVectorStore

pytestmark = [pytest.mark.functional]


def _unit_vector(index: int) -> list[float]:
    """Return a one-hot 1024-dim vector pointing along ``index``."""
    vector = [0.0] * EMBEDDING_DIM
    vector[index % EMBEDDING_DIM] = 1.0
    return vector


class _FakeEmbedding:
    """Deterministic embedding model that maps the i-th text to axis i.

    Avoids loading the real e5-large model in CI.  ``add_document_chunks``
    prefixes texts with ``"passage: "`` before calling ``embed_documents``;
    we ignore the content and key off call order.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_unit_vector(i) for i in range(len(texts))]

    def embed_query(self, text: str) -> list[float]:
        # Tests call similarity_search_by_vector directly, so this is unused.
        return _unit_vector(0)


@pytest.fixture()
def _db(monkeypatch: pytest.MonkeyPatch) -> str:
    db_url = os.environ.get(
        "AIRUNNER_TEST_DATABASE_URL",
        os.environ.get("AIRUNNER_DATABASE_URL"),
    )
    if not db_url:
        pytest.skip("No test database configured (AIRUNNER_TEST_DATABASE_URL)")
    monkeypatch.setenv("AIRUNNER_DATABASE_URL", db_url)
    monkeypatch.setenv("AIRUNNER_DISABLE_DB_SETUP_CACHE", "1")
    reset_engine()
    try:
        setup_database()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Database unavailable: {exc}")
    return db_url


def _cleanup(doc_id: str) -> None:
    PgVectorStore.delete_document(doc_id)


def test_add_and_search_orders_by_cosine(_db: str, tmp_path: Path) -> None:
    from langchain_core.documents import Document

    doc_id = "pgvector-test-doc"
    _cleanup(doc_id)
    try:
        chunks = [
            Document(page_content="alpha chunk", metadata={"file_name": "a"}),
            Document(page_content="beta chunk", metadata={"file_name": "a"}),
            Document(page_content="gamma chunk", metadata={"file_name": "a"}),
        ]
        written = PgVectorStore.add_document_chunks(
            document_id=None,
            doc_id=doc_id,
            documents=chunks,
            embedding_model=_FakeEmbedding(),
        )
        assert written == 3
        assert PgVectorStore.document_chunk_count(doc_id) == 3

        # Query closest to the second chunk's axis (index 1).
        hits = PgVectorStore.similarity_search_by_vector(
            _unit_vector(1), k=3, doc_ids=[doc_id]
        )
        assert hits, "expected at least one hit"
        assert hits[0].document.page_content == "beta chunk"
        # Cosine similarity to the matching one-hot axis is ~1.0.
        assert hits[0].score > 0.99
    finally:
        _cleanup(doc_id)


def test_reindex_is_idempotent(_db: str) -> None:
    from langchain_core.documents import Document

    doc_id = "pgvector-test-reindex"
    _cleanup(doc_id)
    try:
        docs = [Document(page_content="only chunk", metadata={})]
        PgVectorStore.add_document_chunks(None, doc_id, docs, _FakeEmbedding())
        PgVectorStore.add_document_chunks(None, doc_id, docs, _FakeEmbedding())
        # Re-indexing replaces rather than appends.
        assert PgVectorStore.document_chunk_count(doc_id) == 1
    finally:
        _cleanup(doc_id)


def test_chunks_persist_to_database_not_disk(_db: str) -> None:
    from langchain_core.documents import Document

    doc_id = "pgvector-test-persist"
    _cleanup(doc_id)
    try:
        PgVectorStore.add_document_chunks(
            None,
            doc_id,
            [Document(page_content="row exists", metadata={})],
            _FakeEmbedding(),
        )
        with session_scope() as session:
            rows = (
                session.query(DocumentChunk)
                .filter(DocumentChunk.doc_id == doc_id)
                .all()
            )
            assert len(rows) == 1
            assert rows[0].content == "row exists"
            assert rows[0].embedding is not None
    finally:
        _cleanup(doc_id)
