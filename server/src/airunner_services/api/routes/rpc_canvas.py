"""RPC handlers: canvas document + layers."""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.api.routes.events import (
    _rpc_error_response,
    _rpc_register,
)
from airunner_services.api.ws_tenant import resolve_ws_tenant

logger = logging.getLogger(__name__)


def _canvas_auth(kw: dict) -> int | None:
    """Resolve and return the account_id from the WS context.

    Returns None when the socket is unauthenticated — callers must
    reject the request with a 401-equivalent response.
    """
    ws = kw.get("ws")
    if ws is None:
        return None
    _tenant, account_id = resolve_ws_tenant(ws)
    return account_id


@_rpc_register("GET", "/api/v1/canvas/document")
async def _rpc_canvas_doc_get(body: dict, **kwargs: Any) -> dict[str, Any]:
    """Return the saved canvas document string."""
    account_id = _canvas_auth(kwargs)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    try:
        from airunner_services.database.models import CanvasSetting

        record = CanvasSetting.objects.query().first()
        doc = str(record.document) if (record and record.document) else None
        return {"status": 200, "body": {"document": doc}}
    except Exception:
        return {"status": 200, "body": {"document": None}}


@_rpc_register("PUT", "/api/v1/canvas/document")
async def _rpc_canvas_doc_save(body: dict, **kwargs: Any) -> dict[str, Any]:
    """Save the canvas document string."""
    account_id = _canvas_auth(kwargs)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    doc_str: str = body.get("document", "")
    try:
        from airunner_services.database.models import CanvasSetting

        with CanvasSetting.objects.transaction() as tx:
            record = tx.query(CanvasSetting).first()
            if record:
                record.document = doc_str
            else:
                tx.add(CanvasSetting(document=doc_str))
        return {"status": 200, "body": {"status": "saved"}}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="canvas document save failed",
        )


@_rpc_register("GET", "/api/v1/canvas/layers")
async def _rpc_canvas_layers_list(body: dict, **kwargs: Any) -> dict[str, Any]:
    """List all canvas layers."""
    account_id = _canvas_auth(kwargs)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    try:
        from airunner_services.database.models import Layer

        layers = Layer.objects.query().order_by(Layer.order).all()
        return {
            "status": 200,
            "body": {
                "layers": [
                    {
                        "id": layer.id,
                        "name": str(layer.name) if layer.name else "",
                        "visible": bool(layer.visible),
                        "locked": bool(layer.locked),
                        "order": int(layer.order),
                        "opacity": float(layer.opacity or 1.0),
                        "blend_mode": str(layer.blend_mode or "normal"),
                        "canvas_id": str(layer.canvas_id or ""),
                        "thumbnail": layer.thumbnail,
                    }
                    for layer in layers
                ]
            },
        }
    except Exception:
        return {"status": 200, "body": {"layers": []}}
