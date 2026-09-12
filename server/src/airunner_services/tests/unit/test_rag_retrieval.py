"""Unit tests for RAG retrieval mixins.

Covers RAGSearchMixin and RAGIndexingMixin behaviour with mocked
retriever and embedding dependencies.
"""

from __future__ import annotations

from unittest.mock import MagicMock



# ---------------------------------------------------------------------------
# RAGSearchMixin — search() with mocked retriever property
# ---------------------------------------------------------------------------


class TestRAGSearchMixin:
    """search() returns results when a retriever is available."""

    @staticmethod
    def _make_mixin(retriever, logger=None):
        """Build a RAGSearchMixin with a fake retriever property."""
        from airunner_services.llm.managers.agent.mixins.rag_search_mixin import (
            RAGSearchMixin,
        )

        mixin = RAGSearchMixin()
        # RAGSearchMixin reads self.retriever and self.logger — both
        # are properties without setters, so patch them on the instance.
        type(mixin).retriever = property(lambda s: retriever)
        type(mixin).logger = property(lambda s: logger or MagicMock())
        return mixin

    def test_search_returns_results(self) -> None:
        mock_doc = MagicMock()
        mock_doc.page_content = "test content"
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [mock_doc]

        mixin = self._make_mixin(mock_retriever)
        results = mixin.search("test query", k=3)
        assert len(results) == 1
        assert results[0].page_content == "test content"

    def test_search_no_retriever_returns_empty(self) -> None:
        mixin = self._make_mixin(None)
        results = mixin.search("test query")
        assert results == []

    def test_search_exception_returns_empty(self) -> None:
        mock_retriever = MagicMock()
        mock_retriever.retrieve.side_effect = RuntimeError("pg down")
        mixin = self._make_mixin(mock_retriever)
        results = mixin.search("test query")
        assert results == []

    def test_search_respects_k_limit(self) -> None:
        docs = [MagicMock() for _ in range(10)]
        for i, doc in enumerate(docs):
            doc.page_content = f"doc {i}"
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = docs
        mixin = self._make_mixin(mock_retriever)
        results = mixin.search("query", k=3)
        assert len(results) == 3


# ---------------------------------------------------------------------------
# RAGIndexingMixin — empty index
# ---------------------------------------------------------------------------


class TestRAGIndexingMixin:
    """Indexing handles missing files gracefully."""

    def test_no_target_files_no_reader(self) -> None:
        from airunner_services.llm.managers.agent.mixins.rag_indexing_mixin import (
            RAGIndexingMixin,
        )

        mixin = RAGIndexingMixin()
        object.__setattr__(mixin, "logger", MagicMock())
        mixin.target_files = []

        assert mixin.document_reader is None

    def test_no_target_files_documents_empty(self) -> None:
        from airunner_services.llm.managers.agent.mixins.rag_indexing_mixin import (
            RAGIndexingMixin,
        )

        mixin = RAGIndexingMixin()
        object.__setattr__(mixin, "logger", MagicMock())
        mixin.target_files = []

        assert mixin.documents == []
