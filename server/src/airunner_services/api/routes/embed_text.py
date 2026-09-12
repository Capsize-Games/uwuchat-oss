"""Text-embedding HTTP endpoint for external callers (headlesscode).

Exposes AIRunner's native in-process embedding stack (intfloat/e5-large) to
plain HTTP callers as ``POST /api/v1/embed/text`` — the endpoint headlesscode's
``airunner`` embedding backend (src/codesearch/airunner-embedder.ts) calls.

This is deliberately a genuine FastAPI ``APIRouter`` (registered via the
``server_routes_specs`` table), NOT an ``_rpc_register`` handler: the RPC
decorator only registers handlers reachable through the single WebSocket
``/events`` endpoint, and headlesscode is an external Node process making a
plain HTTP call (see the routes/__init__.py "WebSocket-only architecture"
note).

Design notes (resolving the open questions in the implementation spec):

1. Standalone model loading. The embedding model is normally loaded lazily
   through ``RAGPropertiesMixin.embedding`` on an agent instance. Outside a
   full LLM-agent context this module lazily constructs + caches its own
   ``HuggingFaceEmbeddings`` instance the same way the mixin does: model path
   resolved from the persisted ``PathSettings`` row (the ``text_embedding``
   path setting, falling back to the default ``<base>/text/models/llm/
   embedding/intfloat/e5-large``), device auto-selected cuda/mps/cpu,
   embeddings
   normalized. The cache is module-level so repeated calls reuse the loaded
   model (model stays in VRAM after the first request).

2. Symmetric vs asymmetric embeddings. We use the symmetric ``embed_texts``
   helper (no e5 ``passage:``/``query:`` prefixing). The asymmetric e5
   convention measurably helps retrieval quality, but headlesscode's
   ``Embedder.embedBatch`` interface treats chunk- and query-embedding as
   symmetric calls through one method (matching the ``ollama``/``openrouter``
   backends), so the endpoint matches that API-shape simplicity. The route
   accepts an optional ``mode: "passage" | "query"`` param for future
   asymmetric use — when present it applies the e5 prefix via
   ``embed_passages``/``embed_query``.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from airunner_services.settings import AIRUNNER_BASE_PATH

logger = logging.getLogger(__name__)

router = APIRouter()

EMBEDDING_MODEL_ID = "intfloat/e5-large"
EMBEDDING_DIM = 1024

# Module-level cache so the loaded model survives across requests (the
# property on RAGPropertiesMixin caches on the agent; here we cache on the
# module since there is no agent instance).
_embedding_model: Any | None = None
_embedding_lock = threading.Lock()


class EmbedTextRequest(BaseModel):
    """Batch of plain texts to embed."""

    texts: list[str] = Field(min_length=1, max_length=128)
    # Optional e5-style asymmetric mode; when absent, symmetric embedding is
    # used (no prefix) — matching headlesscode's symmetric embedBatch call.
    mode: str | None = Field(default=None, pattern="^(passage|query)$")


class EmbedTextResponse(BaseModel):
    """One embedding vector per input text, in input order."""

    model: str
    embeddings: list[list[float]]


def _resolve_model_path() -> str:
    """Resolve the local e5-large model directory.

    Prefers the persisted ``PathSettings`` ``text_embedding`` path setting
    (the same one ``LLM_FILE_BOOTSTRAP_DATA`` maps for intfloat/e5-large);
    falls back to the conventional default under ``AIRUNNER_BASE_PATH``.
    """
    try:
        from airunner_services.database.models.path_settings import (
            PathSettings,
        )

        row = PathSettings.objects.query().first()
        if row is not None:
            base = os.path.expanduser(
                os.path.join(
                    row.base_path, "text", "models", "llm", "embedding",
                    "intfloat/e5-large",
                )
            )
            if os.path.isdir(base):
                return base
    except Exception as exc:  # pragma: no cover - DB not ready at import time
        logger.warning(
            "PathSettings lookup failed, using default path: %s", exc,
        )

    return os.path.expanduser(
        os.path.join(
            AIRUNNER_BASE_PATH, "text", "models", "llm", "embedding",
            "intfloat/e5-large",
        )
    )


def _model_files_present(model_path: str) -> bool:
    """Check the e5-large model files exist (avoid a silent HF download)."""
    required = ("config.json", "model.safetensors")
    return all(os.path.isfile(os.path.join(model_path, f)) for f in required)


def _get_embedding_model() -> Any:
    """Return the cached HuggingFaceEmbeddings instance, loading it lazily.

    Mirrors ``RAGPropertiesMixin.embedding``'s construction (device
    auto-select, normalize_embeddings=True, local_files_only) so the served
    vectors are consistent with AIRunner's own RAG embeddings.
    """
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    with _embedding_lock:
        if _embedding_model is not None:
            return _embedding_model
        try:
            import torch
            from langchain_huggingface import HuggingFaceEmbeddings

            model_path = _resolve_model_path()
            if not _model_files_present(model_path):
                raise RuntimeError(
                    f"Embedding model files missing at {model_path} — "
                    "the model has not been downloaded yet."
                )

            device = "cpu"
            if torch.cuda.is_available():
                device = "cuda"
            elif (
                hasattr(torch.backends, "mps")
                and torch.backends.mps.is_available()
            ):
                device = "mps"

            logger.info(
                "Initializing embedding model on %s: %s", device, model_path,
            )
            _embedding_model = HuggingFaceEmbeddings(
                model_name=model_path,
                model_kwargs={
                    "device": device,
                    "trust_remote_code": True,
                    "local_files_only": True,
                },
                encode_kwargs={"normalize_embeddings": True},
            )
        except Exception as exc:
            logger.exception("Failed to initialize embedding model")
            raise HTTPException(
                status_code=503,
                detail=f"Embedding model unavailable: {exc}",
            ) from exc
        return _embedding_model


class _PriorityTolerantEmbedder:
    """Wrap the model so ``embed_texts``'s ``priority=`` kwarg is tolerated.

    ``pgvector_store.embed_texts``/``embed_passages``/``embed_query`` all pass
    ``priority=`` through to ``embed_documents``/``embed_query``. Depending on
    the installed langchain-huggingface version this kwarg may or may not be
    accepted; this wrapper swallows it so the shared helpers work regardless.
    """

    def __init__(self, model: Any) -> None:
        self._model = model

    def embed_documents(
        self, texts: list[str], priority: str = "live",
    ) -> list[list[float]]:
        return self._model.embed_documents(texts)

    def embed_query(
        self, text: str, priority: str = "live",
    ) -> list[float]:
        return self._model.embed_query(text)


# nosemgrep: missing-auth-dependency (local tooling endpoint — no user data,
# no tenant/session scoping; mirrors health.py's unauthenticated route pattern)
@router.post("/embed/text", response_model=EmbedTextResponse)
async def embed_text(body: EmbedTextRequest) -> EmbedTextResponse:
    """Embed a batch of texts with AIRunner's native e5-large model."""
    model = _get_embedding_model()
    wrapped = _PriorityTolerantEmbedder(model)

    from airunner_services.llm.managers.agent.pgvector_store import (
        embed_passages,
        embed_query,
        embed_texts,
    )

    try:
        if body.mode == "passage":
            vectors = embed_passages(wrapped, body.texts)
        elif body.mode == "query":
            vectors = [embed_query(wrapped, t) for t in body.texts]
        else:
            vectors = embed_texts(wrapped, body.texts)
    except Exception as exc:
        logger.exception("Embedding failed")
        raise HTTPException(
            status_code=500, detail=f"Embedding failed: {exc}",
        ) from exc

    return EmbedTextResponse(model=EMBEDDING_MODEL_ID, embeddings=vectors)
