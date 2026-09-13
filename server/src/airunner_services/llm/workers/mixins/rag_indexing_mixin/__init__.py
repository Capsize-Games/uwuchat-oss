"""Service-owned RAG and document indexing operations for the LLM worker.

The former monolithic ``rag_indexing_mixin.py`` module was split into
this package so every file stays within the 250-line cap.  Method
groups live in focused submodules:

- ``_base`` — shared helpers, document suffix allow-list, signal codes
- ``_index_all`` — full index-all-documents flow
- ``_index_selected`` — user-selected documents flow
- ``_index_single`` — single-document flow
- ``_embedding`` — embedding-model loading
- ``_status`` — cancellation and progress mirroring

Importing this package keeps the previous import path stable:
``from airunner_services.llm.workers.mixins.rag_indexing_mixin import
RAGIndexingMixin`` still resolves to the composed class below.
"""

from __future__ import annotations

from airunner_services.llm.workers.mixins.rag_indexing_mixin._base import (
    RAGIndexingBase,
)
from airunner_services.llm.workers.mixins.rag_indexing_mixin._embedding import (
    RAGEmbeddingMixin,
)
from airunner_services.llm.workers.mixins.rag_indexing_mixin._index_all import (
    RAGIndexAllMixin,
)
from airunner_services.llm.workers.mixins.rag_indexing_mixin._index_selected import (
    RAGIndexSelectedMixin,
)
from airunner_services.llm.workers.mixins.rag_indexing_mixin._index_single import (
    RAGIndexSingleMixin,
)
from airunner_services.llm.workers.mixins.rag_indexing_mixin._status import (
    RAGStatusMixin,
)


class RAGIndexingMixin(
    RAGIndexAllMixin,
    RAGIndexSelectedMixin,
    RAGIndexSingleMixin,
    RAGEmbeddingMixin,
    RAGStatusMixin,
    RAGIndexingBase,
):
    """Handle RAG indexing requests for the LLM worker."""


__all__ = ["RAGIndexingMixin"]
