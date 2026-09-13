"""Agent-related utilities for LLM operations."""

__all__ = [
    "DocumentBatchLoader",
    "PgVectorStore",
    "RAGMixin",
    "WeatherMixin",
]


def __getattr__(name):
    if name == "DocumentBatchLoader":
        from .document_loader import DocumentBatchLoader

        return DocumentBatchLoader
    if name == "PgVectorStore":
        from .pgvector_store import PgVectorStore

        return PgVectorStore
    if name == "RAGMixin":
        from airunner_services.llm.rag_mixin import RAGMixin

        return RAGMixin
    if name == "WeatherMixin":
        from .weather_mixin import WeatherMixin

        return WeatherMixin
    raise AttributeError(f"module {__name__} has no attribute {name}")
