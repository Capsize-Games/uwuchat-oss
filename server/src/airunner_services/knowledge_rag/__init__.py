"""RAG and embeddings mixin for KnowledgeBase.

Semantic search now uses FHE-encrypted embeddings (CKKS ciphertexts)
instead of pgvector plaintext columns.  The search path pre-filters
candidates in SQL (using only non-sensitive plaintext columns), caps
the candidate set, then computes homomorphic dot products to rank
results.  This closes the embedding-inversion leak — a database dump
without a live session/DEK can no longer extract anything from the
embedding column.

Method groups live in focused submodules:

- ``_base`` — composed mixin + embedding indexing
- ``_tfidf`` — keyword search with TF-IDF fallback
- ``_fhe`` — FHE-encrypted vector similarity search
- ``_helpers`` — fact fetching, chatbot scoping, entity formatting

Importing this package makes ``KnowledgeBaseRAGMixin`` available to
``KnowledgeBase`` and re-exports ``FHE_CANDIDATE_CAP`` for tests.
"""

from __future__ import annotations

from airunner_services.knowledge_rag._base import KnowledgeBaseRAGMixin
from airunner_services.utils.crypto.fhe_search import (
    FHE_CANDIDATE_CAP,
)

__all__ = [
    "FHE_CANDIDATE_CAP",
    "KnowledgeBaseRAGMixin",
]
