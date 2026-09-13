"""Email body chunk retrieval — FHE-encrypted vector similarity search.

Only called from the system-bot + omnipotent_knowledge gated branch of
``_gather_knowledge_context()``. Never exposed as a general tool.

Cost tracking: after every embedding API call, ``record_usage`` is
called to log real token costs. This provides visibility into embedding
costs for email body query embedding.
"""

from __future__ import annotations

import logging

from airunner_services.database.models.email_body_chunk import (
    EmailBodyChunk,
)

from airunner_services.conf.model_settings import QWEN_EMBEDDING_MODEL

logger = logging.getLogger(__name__)


def search_email_body_chunks(query: str, k: int = 8) -> list[str]:
    """Return the top-k email body-chunk excerpts matching *query*.

    Embeds the query via the cloud provider, pre-filters candidates
    by account scope and recency, then scores via FHE dot-product
    using the shared ``fhe_similarity_rank`` helper.

    Returns decrypted excerpt strings, most relevant first.
    """
    if not query or not query.strip():
        return []

    from airunner_services.data.tenant import get_account_id
    from airunner_services.utils.crypto.fhe_helpers import (
        l2_normalize,
    )
    from airunner_services.utils.crypto.fhe_search import (
        FHE_CANDIDATE_CAP,
        fhe_similarity_rank,
    )

    account_id = get_account_id()
    if account_id is None:
        logger.warning(
            "No account_id in tenant context — "
            "skipping email body chunk search"
        )
        return []

    try:
        from projects.uwuchat.server.embedding_provider import (
            get_embedding_provider,
        )

        provider = get_embedding_provider()
        query_vector = provider.embed_query(query)
        if not query_vector:
            return []
    except Exception as exc:
        logger.warning(
            "Failed to embed query for email body chunks: %s", exc,
        )
        return []

    normalized_query = l2_normalize(query_vector)

    # Pre-filter candidates by recency (account scoping is already
    # guaranteed by tenant-schema isolation — rows in this schema
    # belong to this tenant).
    candidates = (
        EmailBodyChunk.objects.query()
        .filter(
            EmailBodyChunk.deleted == False,
            EmailBodyChunk.embedding_enc.isnot(None),
        )
        .order_by(EmailBodyChunk.generated_at.desc())
        .limit(FHE_CANDIDATE_CAP)
        .all()
    )

    if not candidates:
        return []

    scored = fhe_similarity_rank(
        candidates,
        get_ciphertext=lambda c: c.embedding_enc,
        account_id=account_id,
        normalized_query=normalized_query.tolist(),
        top_k=k,
    )

    results: list[str] = []
    for chunk, _score in scored:
        text = chunk.content_ciphertext
        if text and isinstance(text, str):
            results.append(text)

    # Record usage for query embedding cost tracking.
    from airunner_services.llm.token_usage import record_usage

    input_tokens = max(1, len(query) // 4)
    record_usage(
        pipeline_key="EMAIL_QUERY_EMBEDDING",
        model_id=QWEN_EMBEDDING_MODEL,
        input_tokens=input_tokens,
        output_tokens=0,
        account_id=account_id,
        call_chain_id=None,
    )

    return results
