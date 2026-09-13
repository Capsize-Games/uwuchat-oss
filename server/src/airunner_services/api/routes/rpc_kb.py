"""RPC handlers: knowledge-base documents."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from airunner_services.api.routes.events import (
    _rpc_error_response,
    _rpc_register,
)
from airunner_services.api.ws_tenant import resolve_ws_tenant

logger = logging.getLogger(__name__)


def _require_auth(kwargs: dict) -> int | None:
    """Return the account_id for an authenticated WS connection, or None
    if the connection has no resolvable identity."""
    ws = kwargs.get("ws")
    if ws is None:
        return None
    _tenant, account_id = resolve_ws_tenant(ws)
    return account_id


@_rpc_register("GET", "/api/v1/knowledge-base/documents")
async def _rpc_kb_documents(body: dict, **kwargs: Any) -> dict[str, Any]:
    """List all knowledge base documents.

    Syncs the on-disk knowledge-base folder into the *current tenant's*
    Document table first, so the panel reflects the local folder per
    account in dev. In production (filesystem ingestion disabled) the sync
    is a no-op and only uploaded documents are returned.
    """
    if _require_auth(kwargs) is None:
        return {"status": 200, "body": {"documents": []}}
    try:
        from airunner_services.api.routes.knowledge_base_watch import (
            sync_documents,
        )
        from airunner_services.database.models.document import Document

        with Document.objects.transaction() as tx:
            sync_documents(tx.session)
            docs = tx.query(Document).all()
            documents = [
                {
                    "id": d.id,
                    "name": Path(str(d.path)).name if d.path else "",
                    "path": str(d.path) if d.path else "",
                    "indexed": bool(d.indexed),
                    "active": bool(d.active),
                }
                for d in docs
            ]
            return {"status": 200, "body": {"documents": documents}}
    except Exception:
        return {"status": 200, "body": {"documents": []}}


@_rpc_register(
    "PATCH", "/api/v1/knowledge-base/documents/{doc_id}/toggle-active"
)
async def _rpc_kb_toggle_active(body: dict, **kwargs: Any) -> dict[str, Any]:
    """Toggle a document's active state."""
    if _require_auth(kwargs) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    pp: dict = kwargs.get("path_params", {})
    raw_id = pp.get("doc_id", "")
    if not raw_id:
        return {"status": 400, "body": {"error": "Missing document ID"}}
    doc_id = int(raw_id)
    try:
        from airunner_services.database.models.document import Document

        with Document.objects.transaction() as tx:
            doc = tx.query(Document).filter(Document.id == doc_id).first()
            if doc is None:
                return {
                    "status": 404,
                    "body": {"error": "Document not found"},
                }
            doc.active = not doc.active
            return {
                "status": 200,
                "body": {"id": doc.id, "active": bool(doc.active)},
            }
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="kb toggle active failed",
        )


@_rpc_register("POST", "/api/v1/knowledge-base/documents/index-all")
async def _rpc_kb_index_all(body: dict, **kwargs: Any) -> dict[str, Any]:
    """Trigger indexing of all documents."""
    if _require_auth(kwargs) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    from airunner_services.contract_enums import SignalCode
    from airunner_services.utils.application.signal_mediator import (
        SignalMediator,
    )

    force = bool(body.get("force", False)) if body else False
    SignalMediator().emit_signal(
        SignalCode.RAG_INDEX_ALL_DOCUMENTS,
        {"force": force},
    )
    return {"status": 200, "body": {"status": "started"}}


@_rpc_register("POST", "/api/v1/knowledge-base/documents/index-cancel")
async def _rpc_kb_index_cancel(body: dict, **kwargs: Any) -> dict[str, Any]:
    """Cancel indexing."""
    if _require_auth(kwargs) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    from airunner_services.contract_enums import SignalCode
    from airunner_services.utils.application.signal_mediator import (
        SignalMediator,
    )

    SignalMediator().emit_signal(SignalCode.RAG_INDEX_CANCEL, {})
    return {"status": 200, "body": {"status": "cancelled"}}
