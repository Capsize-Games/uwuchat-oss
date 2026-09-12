"""Unified WebSocket endpoint for real-time events + RPC request/response.

Provides a single ``/api/v1/events`` WebSocket that multiplexes:

1. **Event subscriptions** — push events (model status, images, loras,
   embeddings, KB documents, index progress, download progress).
2. **RPC request/response** — replaces HTTP REST calls with WS
   messages that carry a correlation ``id`` and ``method``+``path``.
3. **Binary responses** — images and other binary data are sent as
   native WS binary frames preceded by a JSON metadata frame.

Rate limiting: the RPC dispatch path (``_handle_rpc_message``) is
throttled per account via the shared sliding-window limiter.  Event
subscription messages (subscribe/unsubscribe/ping) are not rate-limited
since they are lightweight and server-initiated push has its own back-
pressure via the drain loop.

Protocol
--------
**Subscribe**::

    {"type": "subscribe", "events": ["model_status", "images"]}
    → {"type": "subscribed", "events": ["model_status", "images"]}

**RPC request**::

    {"type": "rpc", "id": "uuid", "method": "GET",
     "path": "/health", "body": {}}
    → {"type": "rpc_response", "id": "uuid", "status": 200,
       "body": {"status": "ok"}}
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket

from airunner_services.api.routes.events_bus import _WsSubscriber, WsEventBus
from airunner_services.api.routes.events_rpc import (
    _ACCOUNT_SCOPED_EVENTS,
    ALL_EVENTS,
    EVENT_DOCUMENTS,
    EVENT_DOWNLOADS,
    EVENT_EMBEDDINGS,
    EVENT_IMAGES,
    EVENT_INDEX_PROGRESS,
    EVENT_LORAS,
    EVENT_MODEL_STATUS,
    _dispatch_rpc,
    _rpc_error_response,
    _rpc_register,
    _rpc_routes,
)
from airunner_services.api.ws_rate_limiter import (
    check_rpc_rate,
    reset_account_limits,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _json_default(value: Any) -> str:
    """Fallback encoder for types ``json`` can't serialize natively.

    Resource-store RPC handlers build records from every model column,
    which now includes ``BaseModel``'s ``created_at`` / ``updated_at``
    ``datetime`` columns. ``WebSocket.send_json`` raises ``TypeError`` on
    those, and because the receive loop swallows exceptions the whole
    socket is torn down silently. Coercing datetimes (and any other odd
    type) to strings keeps every RPC response serializable.
    """
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    return str(value)


async def _safe_send_json(
    websocket: WebSocket, payload: dict[str, Any]
) -> None:
    """Send a JSON frame, coercing non-serializable values to strings."""
    await websocket.send_text(json.dumps(payload, default=_json_default))


async def _handle_subscribe(
    raw: dict[str, Any],
    websocket: WebSocket,
    subscriber: _WsSubscriber,
    bus: WsEventBus,
) -> None:
    """Process a subscribe message.

    Unauthenticated subscribers (``account_id is None``) are **rejected**
    for account-scoped event types (``proactive_message``,
    ``gems_balance``, ``weather_data``).  Public event types
    (``images``, ``model_status``, etc.) are still allowed without
    authentication.
    """
    events: list[str] = raw.get("events", [])
    if subscriber.account_id is None:
        disallowed = [
            e for e in events if e in _ACCOUNT_SCOPED_EVENTS
        ]
        if disallowed:
            await websocket.send_json(
                {
                    "type": "error",
                    "error": (
                        "Authentication required for account-scoped "
                        "event types: " + ", ".join(sorted(disallowed))
                    ),
                }
            )
            return
    bus.subscribe(subscriber, events)
    await websocket.send_json(
        {
            "type": "subscribed",
            "events": sorted(subscriber.subscriptions),
        }
    )


async def _handle_unsubscribe(
    raw: dict[str, Any],
    websocket: WebSocket,
    subscriber: _WsSubscriber,
    bus: WsEventBus,
) -> None:
    """Process an unsubscribe message."""
    events = raw.get("events", [])
    bus.unsubscribe(subscriber, events)
    await websocket.send_json(
        {
            "type": "unsubscribed",
            "events": sorted(subscriber.subscriptions),
        }
    )


async def _send_rpc_binary(
    response: dict[str, Any],
    result: dict[str, Any],
    websocket: WebSocket,
) -> None:
    """Send an RPC response with a binary data frame."""
    response["binary"] = True
    response["headers"] = result.get("headers", {})
    await _safe_send_json(websocket, response)
    raw_body = result.get("body")
    if isinstance(raw_body, bytes):
        await websocket.send_bytes(raw_body)


async def _handle_ws_message(
    raw: dict[str, Any],
    websocket: WebSocket,
    subscriber: _WsSubscriber,
    bus: WsEventBus,
    account_id: int | None,
) -> None:
    """Process a single incoming WebSocket message."""
    msg_type = raw.get("type", "")

    if msg_type == "subscribe":
        await _handle_subscribe(raw, websocket, subscriber, bus)
    elif msg_type == "unsubscribe":
        await _handle_unsubscribe(raw, websocket, subscriber, bus)
    elif msg_type == "ping":
        await websocket.send_json({"type": "pong"})
    elif msg_type == "rpc":
        await _handle_rpc_message(raw, websocket, account_id)


async def _handle_rpc_message(
    raw: dict[str, Any],
    websocket: WebSocket,
    account_id: int | None,
) -> None:
    """Process an RPC request message and send the response.

    Rate-limited per account (120 calls/min).  The account_id is
    resolved once at connection open (``ws_tenant_scope`` in
    ``unified_events``) and passed in — re-decoding the JWT on every
    RPC message would add a redundant round-trip.  If rate-limited, a
    429 response is sent instead of dispatching to the handler.
    """
    rpc_id = str(raw.get("id", ""))
    method = str(raw.get("method", "GET")).upper()
    path = str(raw.get("path", "/"))
    body = raw.get("body") or {}

    if not check_rpc_rate(account_id):
        response: dict[str, Any] = {
            "type": "rpc_response",
            "id": rpc_id,
            "status": 429,
            "body": {"error": "Rate limit exceeded. Please slow down."},
        }
        await _safe_send_json(websocket, response)
        return

    result = await _dispatch_rpc(method, path, body, websocket)
    response: dict[str, Any] = {
        "type": "rpc_response",
        "id": rpc_id,
        "status": result.get("status", 500),
    }
    if "body" in result:
        response["body"] = result["body"]
    if "error" in result:
        response["error"] = result["error"]
    if result.get("binary"):
        await _send_rpc_binary(response, result, websocket)
    else:
        await _safe_send_json(websocket, response)


async def _cleanup_ws(
    subscriber: _WsSubscriber,
    drain_task: asyncio.Task,
    bus: WsEventBus,
    websocket: WebSocket,
) -> None:
    """Clean up WebSocket subscriber, drain task, and connection.

    Rate-limit state is cleared per account on disconnect so the
    in-memory ``_buckets`` dict does not grow without bound.
    """
    reset_account_limits(subscriber.account_id)
    subscriber.close()
    drain_task.cancel()
    try:
        await drain_task
    except (Exception, asyncio.CancelledError):
        pass
    bus.remove(subscriber)
    try:
        await websocket.close()
    except Exception:
        pass


def _account_has_dek_envelope(account_id: int) -> bool:
    """Return whether *account_id* has a password-derived DEK envelope.

    OAuth-only accounts (Google, Steam) are created with no password and
    so never get a ``wrapped_dek`` — there is no envelope to ever unwrap
    into the cache, which is a different condition from a real cache
    miss on an account that has one.
    """
    from airunner_services.database.session import public_session_scope
    from extensions.auth.server.models import Account

    with public_session_scope() as session:
        account = session.query(Account).filter(
            Account.id == account_id,
        ).first()
        return account is not None and account.wrapped_dek is not None


@router.websocket("/events")
async def unified_events(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time events + RPC request/response."""
    from airunner_services.api.ws_tenant import (
        resolve_ws_tenant,
        ws_dek_scope,
        ws_tenant_scope,
    )

    # Resolve authentication *before* accepting the socket.  Account-scoped
    # event types require an authenticated subscriber; accepting first and
    # checking later would let unauthenticated sockets connect and register
    # for public event types.
    _tenant_key, _initial_account_id = resolve_ws_tenant(websocket)
    await websocket.accept()
    # WS upgrades bypass the HTTP auth middleware, so the JWT→tenant context
    # is established here for the life of the socket. Without it, RPC calls
    # made over this channel (conversation list/select, etc.) query the
    # anonymous schema regardless of the signed-in account.
    #
    # The DEK is resolved *per message* via ws_dek_scope rather than once
    # at connection open — the in-process DEK cache does not survive a
    # server restart and can expire mid-connection.  A one-time lookup would
    # silently break decryption for the rest of the socket's life.
    with ws_tenant_scope(websocket) as (_tenant_key, account_id):
        bus = WsEventBus()
        subscriber = _WsSubscriber(websocket, account_id=account_id)
        drain_task = asyncio.create_task(subscriber.drain_loop())

        # ── Stale encryption session detection ──────────────────────────
        # If the in-memory DEK cache was wiped (e.g. a server restart since
        # this user logged in), every encrypted operation would fail.  The
        # client already handles "force_logout" frames by redirecting to
        # /login, so this is strictly earlier detection of a condition that
        # would otherwise surface minutes later as a failed chat send.
        #
        # This only applies to accounts that actually have a DEK envelope
        # (password-based accounts). OAuth-only accounts (Google, Steam —
        # created with no password, so no wrapped_dek is ever generated)
        # never populate the cache in the first place; treating their
        # permanent cache-miss as "stale" force-logs them out on every
        # single connection.
        stale_session = False
        if account_id is not None and _account_has_dek_envelope(account_id):
            from airunner_services.utils.crypto.dek_cache import cache_get

            if cache_get(account_id) is None:
                stale_session = True
                await _safe_send_json(
                    websocket,
                    {
                        "type": "force_logout",
                        "reason": "encryption_session_expired",
                    },
                )

        # Push bootstrap data immediately after tenant resolution (and
        # after the DEK-staleness check) so the client doesn't need to
        # fire individual singleton/roster RPC calls for session-invariant
        # data.  Skip when the session is about to be force-logged out.
        if not stale_session:
            try:
                from airunner_services.api.routes.events_bootstrap import (
                    build_bootstrap_payload,
                )

                bootstrap = await build_bootstrap_payload(
                    account_id, websocket
                )
                await _safe_send_json(
                    websocket, {"type": "bootstrap", "body": bootstrap}
                )
            except Exception:
                logger.warning(
                    "bootstrap push failed — client will fall back to "
                    "individual RPC calls",
                    exc_info=True,
                )

        try:
            while True:
                raw = await websocket.receive_json()
                with ws_dek_scope(account_id):
                    await _handle_ws_message(
                        raw, websocket, subscriber, bus, account_id
                    )
        except Exception:
            pass
        finally:
            await _cleanup_ws(subscriber, drain_task, bus, websocket)


# ── Re-export for backward compatibility ─────────────────────────────────
__all__ = [
    "WsEventBus",
    "_WsSubscriber",
    "_rpc_error_response",
    "_rpc_register",
    "_rpc_routes",
    "ALL_EVENTS",
    "EVENT_IMAGES",
    "EVENT_LORAS",
    "EVENT_EMBEDDINGS",
    "EVENT_DOCUMENTS",
    "EVENT_MODEL_STATUS",
    "EVENT_INDEX_PROGRESS",
    "EVENT_DOWNLOADS",
]
