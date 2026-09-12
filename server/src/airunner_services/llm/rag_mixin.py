"""Service-owned top-level RAG mixin composition."""

from airunner_services.llm.managers.agent.mixins import (
    RAGDocumentMixin,
    RAGIndexingMixin,
    RAGLifecycleMixin,
    RAGPropertiesMixin,
    RAGSearchMixin,
)


class RAGMixin(
    RAGPropertiesMixin,
    RAGDocumentMixin,
    RAGIndexingMixin,
    RAGSearchMixin,
    RAGLifecycleMixin,
):
    """pgvector-backed RAG implementation with lazy loading."""


__all__ = ["RAGMixin"]
