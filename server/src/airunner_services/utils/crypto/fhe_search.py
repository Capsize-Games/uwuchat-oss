"""Shared, table-agnostic FHE candidate scoring.

Extracted from ``knowledge_rag.py::_fhe_score_candidates`` so that
every table with FHE-encrypted embeddings (``KnowledgeFact``,
``ConversationTurn``, ``EmailBodyChunk``) uses the same loop — one
bug fix in one copy cannot silently leave the others broken.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np

logger = logging.getLogger(__name__)


# Maximum candidates scored with FHE before returning top-k.
# Homomorphic dot products are orders of magnitude slower than the
# pgvector operator they replace, and there is no ciphertext equivalent
# of an ANN index (HNSW/IVF).  Cost scales linearly with candidate
# count, so we conservatively cap at 100 and order by recency as a
# cheap pre-ranking signal.
FHE_CANDIDATE_CAP: int = 100
"""Maximum number of candidates scored with FHE per search query."""


def fhe_similarity_rank(
    candidates: list[Any],
    get_ciphertext: Callable[[Any], bytes | None],
    account_id: int,
    normalized_query: list[float],
    top_k: int,
) -> list[tuple[Any, float]]:
    """Score *candidates* via FHE dot-product, return top-k sorted.

    Args:
        candidates: Pre-filtered rows with non-NULL embedding_enc.
        get_ciphertext: Callable extracting ``embedding_enc`` bytes
            from a single row (``row → bytes | None``).
        account_id: Account ID for FHE secret-context resolution.
        normalized_query: L2-normalized query vector (plaintext).
        top_k: Max results to return. The full list is scored but
            only the top *top_k* are returned.

    Returns:
        List of ``(row, score)`` sorted by score descending,
        at most *top_k* entries.
    """
    from airunner_services.utils.crypto.fhe_helpers import (
        compute_encrypted_dot_product,
        decrypt_scalar,
        deserialize_ciphertext,
    )
    from airunner_services.utils.crypto.fhe_cache import (
        fhe_cache_get,
    )
    from airunner_services.utils.crypto.fhe_key_wrap import (
        unwrap_secret_context,
    )
    from airunner_services.database.models.fhe_key_material import (
        FheKeyMaterial,
    )
    from airunner_services.utils.crypto.dek_cache import (
        get_user_dek,
    )

    if top_k <= 0:
        return []

    # Get the secret context (cached or unwrap from DB).
    secret_ctx = fhe_cache_get(account_id)
    if secret_ctx is None:
        row = FheKeyMaterial.objects.query().filter(
            FheKeyMaterial.account_id == account_id,
        ).first()
        if row is None:
            logger.warning(
                "No FHE key material for account %d — "
                "skipping FHE search",
                account_id,
            )
            return []
        dek = get_user_dek()
        if dek is None:
            logger.warning(
                "No DEK available for account %d — "
                "skipping FHE search",
                account_id,
            )
            return []
        secret_ctx = unwrap_secret_context(
            row.secret_key_wrapped, dek,
        )

    query_arr = np.array(normalized_query, dtype=np.float64)
    scored: list[tuple[Any, float]] = []
    for candidate in candidates:
        ciphertext = get_ciphertext(candidate)
        if ciphertext is None:
            continue
        try:
            ct_vec = deserialize_ciphertext(ciphertext, secret_ctx)
            enc_scalar = compute_encrypted_dot_product(
                ct_vec, query_arr,
            )
            score = decrypt_scalar(enc_scalar, secret_ctx)
            scored.append((candidate, score))
        except Exception as exc:
            logger.error(
                "FHE scoring failed for candidate: %s", exc,
            )
            continue
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


__all__ = [
    "FHE_CANDIDATE_CAP",
    "fhe_similarity_rank",
]
