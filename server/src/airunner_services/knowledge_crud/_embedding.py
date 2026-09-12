"""Embedding helpers for knowledge facts (plaintext and FHE).

``_compute_embedding`` computes one plaintext embedding vector and
records token usage for cost tracking after every successful API call.

``_compute_fhe_embedding`` L2-normalizes the vector, encrypts it with
the account's FHE public context, and serializes the ciphertext for
``KnowledgeFact.embedding_enc``.  It fails closed: raises
``DataEncryptionError`` when an embedding is requested but no
``account_id`` is resolvable.

TenSEAL-dependent imports are deliberately lazy (inside function
bodies) so that importing this package never requires TenSEAL — only
the code paths that actually encrypt embeddings do.
"""

from __future__ import annotations

import logging
from typing import Optional

from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError,
)

logger = logging.getLogger(__name__)


def _compute_embedding(
    embedding_model,
    fact: str,
    account_id: Optional[int] = None,
    tenant_key: Optional[str] = None,
) -> Optional[list[float]]:
    """Compute one plaintext embedding vector for *fact*.

    Returns the embedding vector, or None if embedding_model is None
    or the embedding call fails.

    Records token usage for cost tracking after successful embedding.
    Uses the actual model name from the provider (``_model`` attribute)
    when available, falling back to a generic label.
    """
    if embedding_model is None:
        return None
    try:
        from airunner_services.llm.managers.agent.pgvector_store import (
            embed_passages,
        )
        from airunner_services.llm.token_usage import record_usage

        vectors = embed_passages(embedding_model, [fact])
        vector = vectors[0] if vectors else None

        if vector is not None:
            input_tokens = max(1, len(fact) // 4)
            resolved_model = getattr(
                embedding_model, "_model",
                "unknown-embedding-model",
            )
            record_usage(
                pipeline_key="KNOWLEDGE_FACT_EMBEDDING",
                model_id=resolved_model,
                input_tokens=input_tokens,
                output_tokens=0,
                account_id=account_id,
                tenant_key=tenant_key,
                call_chain_id=None,
            )

        return vector
    except Exception:
        return None


def _get_or_create_public_context(account_id: int):
    """Return the TenSEAL public context for *account_id*.

    Delegates to the shared ``get_or_create_public_context`` in
    ``fhe_account_context.py``.  Kept as a re-export for backward
    compatibility with callers in ``knowledge_rag.py``.
    """
    from airunner_services.utils.crypto.fhe_account_context import (
        get_or_create_public_context,
    )

    return get_or_create_public_context(account_id)


def _compute_fhe_embedding(
    embedding_model,
    fact: str,
    account_id: Optional[int] = None,
    tenant_key: Optional[str] = None,
) -> Optional[bytes]:
    """Compute and encrypt one embedding vector for *fact*.

    Returns the serialized CKKS ciphertext bytes suitable for storage
    in ``KnowledgeFact.embedding_enc``, or None if *embedding_model*
    is None or the embedding call fails.

    Steps:
        1. Compute plaintext embedding via :func:`_compute_embedding`.
        2. L2-normalize the vector.
        3. Encrypt with the account's FHE public context.
        4. Serialize and return ciphertext bytes.

    Fails closed: raises :class:`DataEncryptionError` if *account_id*
    is provided but no DEK is available for FHE key material creation.
    """
    vector = _compute_embedding(
        embedding_model, fact,
        account_id=account_id,
        tenant_key=tenant_key,
    )
    if vector is None:
        return None

    from airunner_services.data.tenant import get_account_id
    from airunner_services.utils.crypto.fhe_helpers import (
        encrypt_embedding,
        l2_normalize,
    )

    normalized = l2_normalize(vector)

    resolved_id = account_id or get_account_id()
    if resolved_id is None:
        raise DataEncryptionError(
            "FHE embedding encryption requires an account_id. "
            "No account_id was provided and none is active in the "
            "tenant context. The caller must run within a tenant "
            "scope that sets the account ID via "
            "airunner_services.data.tenant.set_account_id()."
        )

    try:
        public_ctx = _get_or_create_public_context(resolved_id)
        return encrypt_embedding(normalized, public_ctx)
    except DataEncryptionError:
        raise
    except Exception as exc:
        logger.error(
            "FHE encryption failed for account %d: %s",
            resolved_id, exc,
        )
        return None
