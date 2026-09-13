"""Cloud embedding provider — OpenRouter-hosted embedding model.

Implements the duck-typed interface expected by ``pgvector_store.py``:
  - ``embed_documents(texts) -> list[list[float]]``
  - ``embed_query(text) -> list[float]``

Constructs lazily from the ``"EMBEDDING"`` entry in
``projects/uwuchat/server/ai_pipeline.py``.  Requests 1024-dim output
(via Matryoshka-style ``dimensions`` parameter) to match the existing
``EMBEDDING_DIM = 1024`` in ``document_chunk.py`` — no schema migration
required.

As of 2026-07, concurrency is gated by a **distributed Redis-backed
priority-lane limiter** rather than a per-process ``threading.Semaphore``.
See ``plans/uwuchat-embedding-rate-limit-priority-lanes.md`` and
``airunner_services.cloud.distributed_limiter`` for the full design.
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import List, Literal

import httpx
from airunner_services.conf.model_settings import QWEN_EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"

# Transient failures (rate limiting, provider-side overload) must not
# be treated as permanent — observed in production as OpenRouter/
# DeepInfra returning 429 "Model busy, retry later" under sustained
# concurrent load from batched indexing.  Retried with exponential
# backoff + jitter; anything else (4xx auth/payload errors) fails
# immediately since retrying won't help.
_MAX_RETRIES = 5
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 30.0
_EMBEDDING_DIM = 1024
_DEFAULT_MODEL = QWEN_EMBEDDING_MODEL
_BATCH_SIZE = 100  # OpenAI embeddings API accepts up to 2048 inputs/batch


class OpenRouterEmbeddingProvider:
    """Thin wrapper around OpenRouter's OpenAI-compatible embeddings API.

    Matches the interface expected by ``embed_passages()`` /
    ``embed_texts()`` / ``embed_query()`` in ``pgvector_store.py``
    so existing call sites can swap the local e5-large model for this
    cloud provider without changing their own logic.

    Concurrency is gated by
    ``airunner_services.cloud.distributed_limiter`` — a Redis-backed
    priority-lane semaphore shared across all worker processes.
    """

    def __init__(self, model: str | None = None) -> None:
        """Resolve model name from pipeline config or fall back default."""
        if model is None:
            model = _resolve_model_name()
        self._model = model
        self._api_key: str | None = None

    @property
    def api_key(self) -> str:
        """Lazily resolve the API key from the environment."""
        if self._api_key is None:
            self._api_key = os.environ.get(
                "OPENROUTER_API_KEY", "",
            )
        return self._api_key

    def embed_documents(
        self,
        texts: List[str],
        priority: Literal["live", "bulk"] = "live",
    ) -> List[List[float]]:
        """Embed a batch of documents (the duck-typed interface).

        Batches internally to stay within API limits.  *priority*
        selects the admission lane — default ``"live"`` so callers
        that forget to specify it get live-lane treatment (fail-safe
        rather than accidentally starving interactive traffic).
        """
        if not texts:
            return []
        all_vectors: List[List[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i:i + _BATCH_SIZE]
            vectors = self._call_api(batch, priority=priority)
            all_vectors.extend(vectors)
        return all_vectors

    def embed_query(
        self,
        text: str,
        priority: Literal["live", "bulk"] = "live",
    ) -> List[float]:
        """Embed a single query string.

        *priority* selects the admission lane — default ``"live"``.
        """
        if not text:
            return []
        vectors = self._call_api([text], priority=priority)
        return vectors[0] if vectors else []

    def _call_api(
        self,
        inputs: List[str],
        priority: Literal["live", "bulk"] = "live",
    ) -> List[List[float]]:
        """POST to OpenRouter embeddings, returning parsed vectors.

        Retries transient failures (rate limiting, provider-side
        overload) with exponential backoff + jitter — a 429 "model
        busy" response is not a permanent failure, and treating it
        as one silently discards real, already-paid-for work (see
        ``_MAX_RETRIES`` docstring above).

        Admission is gated by the distributed Redis limiter:
        live-lane callers get a short bounded wait then degrade
        (return empty); bulk-lane callers retry with the existing
        backoff mechanism until a slot is available.
        """
        from airunner_services.cloud.distributed_limiter import (
            acquire_slot,
            acquire_with_retry,
        )
        from airunner_services.data.tenant import get_tenant_key

        tenant_key = _resolve_tenant_key()

        payload = {
            "model": self._model,
            "input": inputs,
            "dimensions": _EMBEDDING_DIM,
            # Pinned to DeepInfra specifically — zero data retention
            # and lower cost than the account's other allowed
            # providers for this model; no fallback to a provider
            # that wasn't chosen for those reasons.
            "provider": {
                "order": ["DeepInfra"],
                "allow_fallbacks": False,
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            # --- Acquire a distributed concurrency slot ---
            if priority == "live":
                slot = acquire_with_retry(
                    "embedding", "live", tenant_key,
                )
                if slot is None:
                    logger.debug(
                        "Embedding live lane full — "
                        "degrading gracefully (no results)"
                    )
                    return []
            else:
                slot = acquire_slot("embedding", "bulk", tenant_key)
                if slot is None and attempt < _MAX_RETRIES:
                    self._sleep_before_retry(attempt, RuntimeError(
                        "Embedding bulk lane full — waiting for slot"
                    ))
                    continue
                if slot is None:
                    logger.warning(
                        "Embedding bulk lane still full after %d "
                        "retries — giving up", _MAX_RETRIES,
                    )
                    return []

            try:
                response = httpx.post(
                    _OPENROUTER_EMBEDDINGS_URL,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )
            except httpx.TransportError as exc:
                slot.release()
                last_exc = exc
                if attempt >= _MAX_RETRIES:
                    raise
                self._sleep_before_retry(attempt, exc)
                continue

            if response.status_code == 200:
                slot.release()
                data = response.json()
                return [
                    item["embedding"]
                    for item in data.get("data", [])
                    if "embedding" in item
                ]

            slot.release()
            error = RuntimeError(
                f"OpenRouter embeddings returned {response.status_code}: "
                f"{response.text[:200]}"
            )
            if (
                response.status_code not in _RETRYABLE_STATUS_CODES
                or attempt >= _MAX_RETRIES
            ):
                raise error
            last_exc = error
            self._sleep_before_retry(
                attempt, error, retry_after=response.headers.get(
                    "retry-after",
                ),
            )

        # Unreachable in practice — the loop always returns or raises —
        # but keeps type checkers happy and fails loudly if it's ever
        # wrong instead of returning something silently incorrect.
        raise last_exc or RuntimeError(
            "Embedding request failed with no captured exception",
        )

    @staticmethod
    def _sleep_before_retry(
        attempt: int,
        exc: Exception,
        retry_after: str | None = None,
    ) -> None:
        """Back off before the next retry attempt.

        Honors a numeric ``Retry-After`` header when the provider
        sends one; otherwise falls back to exponential backoff with
        jitter, capped at ``_BACKOFF_MAX_SECONDS``.
        """
        delay: float
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = _BACKOFF_BASE_SECONDS * (2 ** attempt)
        else:
            delay = _BACKOFF_BASE_SECONDS * (2 ** attempt)
        delay = min(delay, _BACKOFF_MAX_SECONDS)
        delay += random.uniform(0, delay * 0.25)

        logger.warning(
            "Embedding API call failed (attempt %d/%d): %s — "
            "retrying in %.1fs",
            attempt + 1, _MAX_RETRIES + 1, exc, delay,
        )
        time.sleep(delay)


def _resolve_tenant_key() -> str:
    """Return the current tenant key for distributed limiter use.

    Returns "" when tenant context is unavailable (e.g. during
    early startup) — the limiter skips per-tenant capping in that
    case while still enforcing lane-level limits.
    """
    try:
        from airunner_services.data.tenant import get_tenant_key

        return get_tenant_key() or ""
    except Exception:
        return ""


def _resolve_model_name() -> str:
    """Look up the model name from pipeline_config("EMBEDDING")."""
    try:
        from airunner_services.llm.pipeline_loader import pipeline_config

        cfg = pipeline_config("EMBEDDING")
        return cfg.get("model", _DEFAULT_MODEL)
    except Exception:
        return _DEFAULT_MODEL


_provider: OpenRouterEmbeddingProvider | None = None


def get_embedding_provider() -> OpenRouterEmbeddingProvider:
    """Return the module-level singleton cloud embedding provider."""
    global _provider

    if _provider is None:
        _provider = OpenRouterEmbeddingProvider()
    return _provider
