"""RPC handlers: embeddings."""

from __future__ import annotations

from typing import Any

from airunner_services.api.routes.events import (
    _rpc_error_response,
    _rpc_register,
)

import logging

logger = logging.getLogger(__name__)


def _sync_current_tenant_embeddings() -> None:
    """Best-effort sync of on-disk embeddings into the current tenant schema.

    In multi-tenant mode the startup scan is deferred (it would target the
    anonymous schema), so the first authenticated read populates the caller's
    tenant here.
    """
    try:
        from airunner_services.database.models.embedding import Embedding
        from airunner_services.database.session import session_scope
        from airunner_services.database.scan_helpers import scan_embeddings
        from airunner_services.settings import AIRUNNER_BASE_PATH

        scan_embeddings(AIRUNNER_BASE_PATH, Embedding, session_scope)
    except Exception as exc:
        logger.warning("Embedding tenant sync skipped: %s", exc)


def _split_trigger_words(value: Any) -> list[str]:
    """Normalize a stored trigger_words value into a list of words."""
    if isinstance(value, list):
        return [str(w).strip() for w in value if str(w).strip()]
    if not value:
        return []
    return [w.strip() for w in str(value).split(",") if w.strip()]


def _join_trigger_words(value: Any) -> str:
    """Normalize an incoming trigger_words value to the stored string form."""
    if isinstance(value, list):
        return ",".join(str(w).strip() for w in value if str(w).strip())
    return str(value or "")


def _embedding_dict(item) -> dict:
    """Build an embedding response dict from one row."""
    return {
        "id": item.id,
        "name": item.name or "",
        "path": item.path or "",
        "enabled": bool(item.enabled),
        "trigger_words": _split_trigger_words(item.trigger_words),
    }


@_rpc_register("GET", "/api/v1/art/embeddings")
async def _rpc_embeddings_list(body: dict, **kw: Any) -> dict[str, Any]:
    """List all embeddings."""
    try:
        from airunner_services.database.models.embedding import Embedding

        _sync_current_tenant_embeddings()
        items = Embedding.objects.query().all()
        return {
            "status": 200,
            "body": {"embeddings": [_embedding_dict(item) for item in items]},
        }
    except Exception:
        return {"status": 200, "body": {"embeddings": []}}


@_rpc_register("PATCH", "/api/v1/art/embeddings/{embedding_id}")
async def _rpc_embeddings_update(body: dict, **kw: Any) -> dict[str, Any]:
    """Update an embedding."""
    pp: dict = kw.get("path_params", {})
    raw_id = pp.get("embedding_id", "")
    if not raw_id.isdigit():
        return {"status": 400, "body": {"error": "Invalid ID"}}
    try:
        from airunner_services.database.models.embedding import Embedding

        emb_id = int(raw_id)
        with Embedding.objects.transaction() as tx:
            item = tx.query(Embedding).filter(Embedding.id == emb_id).first()
            if not item:
                return {"status": 404, "body": {"error": "Not found"}}
            for key in ("enabled", "trigger_words"):
                if key in body:
                    value = (
                        _join_trigger_words(body[key])
                        if key == "trigger_words"
                        else body[key]
                    )
                    setattr(item, key, value)
            return {"status": 200, "body": _embedding_dict(item)}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="embeddings update failed",
        )
