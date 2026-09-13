"""CRUD operations for the knowledge base (add, update, delete facts).

This package provides fail-closed guards for all KnowledgeFact write
operations. Each operation checks that a per-user DEK is available
before touching the encrypted ``fact_text`` column. Writes fall back
silently to weaker keys (global keyring or plaintext) — the guard in
:mod:`_base` prevents that silent fallback by raising
``DataEncryptionError`` instead.

Submodules:

- ``_base`` — DEK guard and shared write helpers
- ``_write`` — add/update fact write paths
- ``_delete`` — soft-delete write path
- ``_tags`` — tag normalisation and linking
- ``_embedding`` — plaintext/FHE embedding helpers

Reads via ``UserEncryptedText.process_result_value`` already have
fail-closed behavior (raise when ciphertext can't be decrypted).

Cost tracking: after every embedding API call, ``record_usage`` is
called to log real token costs. This provides visibility into
embedding costs for KnowledgeFact embedding.
"""

from __future__ import annotations

import logging

# Redundant aliases mark intentional re-exports (names consumers
# import from the package, e.g. lazy imports in embedding_backfill.py
# and knowledge_rag/_base.py, and string patch targets in tests).
from airunner_services.knowledge_crud._base import (
    KnowledgeBaseCrudBase,
    _link_new_fact_relations as _link_new_fact_relations,
    _resolve_event_dates as _resolve_event_dates,
)
from airunner_services.knowledge_crud._delete import (
    KnowledgeBaseDeleteMixin,
)
from airunner_services.knowledge_crud._embedding import (
    _compute_embedding,
    _compute_fhe_embedding,
    _get_or_create_public_context as _get_or_create_public_context,
)
from airunner_services.knowledge_crud._tags import (
    KnowledgeBaseTagMixin,
    _normalise_tags as _normalise_tags,
)
from airunner_services.knowledge_crud._write import (
    KnowledgeBaseWriteMixin,
)
from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError as DataEncryptionError,
)
from airunner_services.utils.crypto.dek_cache import (
    get_user_dek as get_user_dek,
)

logger = logging.getLogger(__name__)


class KnowledgeBaseCrudMixin(
    KnowledgeBaseWriteMixin,
    KnowledgeBaseDeleteMixin,
    KnowledgeBaseTagMixin,
    KnowledgeBaseCrudBase,
):
    """Add, update, and delete knowledge facts."""


__all__ = [
    "KnowledgeBaseCrudMixin",
    "_compute_embedding",
    "_compute_fhe_embedding",
]
