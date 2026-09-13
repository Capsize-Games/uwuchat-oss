"""Canvas document persistence endpoints for Konva JSON serialization."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from airunner_services.database.models.canvas_document import CanvasDocument
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

router = APIRouter()
logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

# Track connected clients per account for tenant-scoped broadcasting.
# Key: account_id, Value: set of WebSocket connections for that account.
_connected_clients: dict[int, set[WebSocket]] = {}


class CanvasDocumentResponse(BaseModel):
    """Response payload for the canvas document."""

    document: Optional[str] = None


class CanvasDocumentPutRequest(BaseModel):
    """Request payload to store the canvas document."""

    document: str


class CanvasDocumentPutResponse(BaseModel):
    """Response payload after storing the canvas document."""

    status: str


async def _broadcast_raw(
    payload: dict, sender: WebSocket, account_id: int,
) -> None:
    """Send a raw dict payload to all connected clients in the same
    account except the sender."""
    clients = _connected_clients.get(account_id, set())
    stale: list[WebSocket] = []
    for client in list(clients):
        if client is sender:
            continue
        try:
            await client.send_json(payload)
        except Exception:
            stale.append(client)
    for s in stale:
        clients.discard(s)


async def _broadcast_document(
    document: str, sender: WebSocket, account_id: int,
) -> None:
    """Send a document update to same-account clients except sender."""
    await _broadcast_raw(
        {"type": "document", "document": document}, sender, account_id,
    )


async def _send_current_document(websocket: WebSocket) -> None:
    """Fetch the latest document from the DB and push it to *websocket*."""
    record = (
        CanvasDocument.objects.query()
        .order_by(CanvasDocument.id.desc())
        .first()
    )
    current_doc = record.document if record is not None else None
    await websocket.send_json(
        {
            "type": "document",
            "document": current_doc,
        }
    )


def _persist_document(doc: str) -> None:
    """Upsert the given document string into the database."""
    with CanvasDocument.objects.transaction() as tx:
        record = (
            tx.query(CanvasDocument).order_by(CanvasDocument.id.desc()).first()
        )
        if record is None:
            record = CanvasDocument(document=doc)
            tx.add(record)
        else:
            record.document = doc
        tx.flush()


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.websocket("/ws")
async def canvas_document_websocket(websocket: WebSocket):
    """WebSocket endpoint for instant canvas document sync.

    On connect, sends the current stored document.
    On each JSON message with {"document": "..."}, persists immediately
    and broadcasts to all other connected clients **in the same
    account**.
    """
    from airunner_services.api.ws_tenant import (
        resolve_ws_tenant,
        ws_dek_scope,
        ws_tenant_scope,
    )

    # Reject unauthenticated sockets before accepting.
    _tenant_key, account_id = resolve_ws_tenant(websocket)
    if account_id is None:
        await websocket.close(code=4001, reason="Authentication required")
        logger.warning(
            "Canvas WS rejected — missing or invalid token"
        )
        return

    await websocket.accept()
    with ws_tenant_scope(websocket) as (_tenant_key, account_id):
        scope = _connected_clients.setdefault(account_id, set())
        scope.add(websocket)
        logger.info(
            "Canvas WS connected account_id=%s (%d for account)",
            account_id,
            len(scope),
        )

        try:
            await _send_current_document(websocket)

            while True:
                data = await websocket.receive_json()

                # Relay live-stroke/stroke-end messages without persistence.
                msg_type = data.get("type")
                if msg_type in ("stroke:live", "stroke:end"):
                    with ws_dek_scope(account_id):
                        await _broadcast_raw(
                            data, sender=websocket, account_id=account_id,
                        )
                    continue

                with ws_dek_scope(account_id):
                    doc = data.get("document")
                    if doc is None:
                        continue

                    _persist_document(doc)

                    # Broadcast to same-account connected clients.
                    await _broadcast_document(
                        doc, websocket, account_id,
                    )
        except WebSocketDisconnect:
            logger.info(
                "Canvas WebSocket disconnected (%d remaining)",
                len(_connected_clients) - 1,
            )
        except Exception as exc:
            logger.error("Canvas document WebSocket error: %s", exc)
        finally:
            scope = _connected_clients.get(account_id, set())
            scope.discard(websocket)
            if not scope:
                _connected_clients.pop(account_id, None)
            try:
                await websocket.close()
            except Exception:
                pass


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/document", response_model=CanvasDocumentResponse)
async def get_canvas_document():
    """Return the stored Konva canvas document JSON blob."""
    record = (
        CanvasDocument.objects.query()
        .order_by(CanvasDocument.id.desc())
        .first()
    )
    if record is None:
        return CanvasDocumentResponse(document=None)
    return CanvasDocumentResponse(document=record.document)


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.put("/document", response_model=CanvasDocumentPutResponse)
async def put_canvas_document(body: CanvasDocumentPutRequest):
    """Store the Konva canvas document JSON blob."""
    with CanvasDocument.objects.transaction() as tx:
        record = (
            tx.query(CanvasDocument).order_by(CanvasDocument.id.desc()).first()
        )
        if record is None:
            record = CanvasDocument(document=body.document)
            tx.add(record)
        else:
            record.document = body.document
        tx.flush()
    return CanvasDocumentPutResponse(status="ok")
