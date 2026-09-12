"""Admin API endpoints for the conversation event audit log."""

from __future__ import annotations

from typing import Any

from airunner_services.api.routes.events import _rpc_register


def _require_superuser(ws: Any) -> int | None:
    """Return the authenticated account_id if superuser, or None.

    Returns None to signal 403 — caller should return immediately.
    """
    try:
        from airunner_services.api.ws_tenant import resolve_ws_tenant

        _tenant, account_id = resolve_ws_tenant(ws)
        if account_id is None:
            return None
        from extensions.auth.server.models import Account

        acct = Account.objects.get(account_id)
        if acct is None or not getattr(acct, "is_superuser", False):
            return None
        return account_id
    except Exception:
        return None


@_rpc_register("GET", "/api/v1/admin/events")
async def _admin_events_list(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """List conversation events, optionally filtered.

    Query params in *body* (or merged from URL):
        chatbot_id (required), since (ISO datetime),
        until (ISO datetime), event_types (comma list),
        limit (default 200), offset (default 0)
    """
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {
            "status": 403,
            "body": {"error": "Superuser required"},
        }

    chatbot_id_raw = body.get("chatbot_id")
    if not chatbot_id_raw:
        return {
            "status": 400,
            "body": {"error": "chatbot_id is required"},
        }
    try:
        chatbot_id = int(chatbot_id_raw)
    except (TypeError, ValueError):
        return {
            "status": 400,
            "body": {"error": "chatbot_id must be an integer"},
        }

    limit = int(body.get("limit", 200))
    offset = int(body.get("offset", 0))
    since = _parse_iso_datetime(body.get("since"))
    until = _parse_iso_datetime(body.get("until"))
    event_types_raw = body.get("event_types")

    # If parsing failed for a non-None value, return 400.
    since_raw = body.get("since")
    until_raw = body.get("until")
    if (since_raw and since is None) or (until_raw and until is None):
        bad = "since" if (since_raw and since is None) else "until"
        return {
            "status": 400,
            "body": {
                "error": (
                    f"'{bad}' must be an ISO-8601 datetime "
                    "(e.g. '2026-07-06T13:06:25.932Z')"
                )
            },
        }

    from airunner_services.database.models.conversation_event import (
        ConversationEvent,
    )

    query = ConversationEvent.objects.query().filter(
        ConversationEvent.chatbot_id == chatbot_id,
    )

    if since is not None:
        query = query.filter(ConversationEvent.created_at >= since)
    if until is not None:
        query = query.filter(ConversationEvent.created_at <= until)
    if event_types_raw:
        types = [t.strip() for t in str(event_types_raw).split(",") if t.strip()]
        if types:
            query = query.filter(
                ConversationEvent.event_type.in_(types),
            )

    total = query.count()
    events = (
        query.order_by(ConversationEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "status": 200,
        "body": {
            "events": [
                {
                    "event_id": str(e.event_id),
                    "event_type": e.event_type,
                    "actor": e.actor,
                    "payload": e.payload,
                    "created_at": e.created_at.isoformat()
                    if e.created_at
                    else None,
                    "sequence_num": e.sequence_num,
                    "conversation_id": e.conversation_id,
                    "session_id": e.session_id,
                }
                for e in events
            ],
            "total": total,
        },
    }


@_rpc_register("GET", "/api/v1/admin/events/{event_id}/context")
async def _admin_events_context(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Return surrounding events and projected conversation state.

    Path param: event_id (UUID)
    """
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {
            "status": 403,
            "body": {"error": "Superuser required"},
        }

    pp: dict = kw.get("path_params", {})
    event_id_str = pp.get("event_id", "")
    if not event_id_str:
        return {
            "status": 400,
            "body": {"error": "event_id is required"},
        }

    import uuid as _uuid

    try:
        event_uuid = _uuid.UUID(event_id_str)
    except ValueError:
        return {
            "status": 400,
            "body": {"error": "Invalid event_id UUID"},
        }

    from airunner_services.database.models.conversation_event import (
        ConversationEvent,
    )

    target = ConversationEvent.objects.query().filter(
        ConversationEvent.event_id == event_uuid,
    ).first()
    if target is None:
        return {
            "status": 404,
            "body": {"error": "Event not found"},
        }

    base_query = ConversationEvent.objects.query().filter(
        ConversationEvent.chatbot_id == target.chatbot_id,
    )

    before = (
        base_query.filter(
            ConversationEvent.created_at < target.created_at,
        )
        .order_by(ConversationEvent.created_at.desc())
        .limit(10)
        .all()
    )
    after = (
        base_query.filter(
            ConversationEvent.created_at > target.created_at,
        )
        .order_by(ConversationEvent.created_at.asc())
        .limit(10)
        .all()
    )

    # Replay events up to and including the target to project the state.
    replay = (
        base_query.filter(
            ConversationEvent.created_at <= target.created_at,
        )
        .order_by(ConversationEvent.created_at.asc())
        .all()
    )

    from airunner_services.events.projector import project_state

    event_dicts = [
        {
            "event_id": str(e.event_id),
            "event_type": e.event_type,
            "actor": e.actor,
            "payload": e.payload,
            "created_at": e.created_at.isoformat()
            if e.created_at
            else None,
            "sequence_num": e.sequence_num,
            "conversation_id": e.conversation_id,
            "session_id": e.session_id,
        }
        for e in replay
    ]
    projected = project_state(event_dicts)

    return {
        "status": 200,
        "body": {
            "before": [
                _serialize_event(e) for e in reversed(before)
            ],
            "after": [_serialize_event(e) for e in after],
            "projected_state": projected,
        },
    }


def _parse_iso_datetime(raw: Any) -> Any:
    """Parse an ISO-8601 datetime string into a timezone-aware
    datetime, or return None when *raw* is None/empty.

    Handles the ``Z`` UTC suffix that Python's ``fromisoformat``
    rejects on the target versions by replacing it with ``+00:00``.
    Returns None for any unparseable value so the caller can
    produce a clean 400.
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(stripped)
    except ValueError:
        pass
    # Retry with Z→+00:00 substitution for UTC-suffix timestamps.
    if stripped.endswith("Z"):
        try:
            return datetime.fromisoformat(
                stripped[:-1] + "+00:00"
            )
        except ValueError:
            pass
    return None


def _serialize_event(e: Any) -> dict[str, Any]:
    """Convert a ConversationEvent ORM instance to a dict."""
    return {
        "event_id": str(e.event_id),
        "event_type": e.event_type,
        "actor": e.actor,
        "payload": e.payload,
        "created_at": e.created_at.isoformat()
        if e.created_at
        else None,
        "sequence_num": e.sequence_num,
        "conversation_id": e.conversation_id,
        "session_id": e.session_id,
    }
