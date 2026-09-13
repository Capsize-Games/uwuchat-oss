"""Admin route: view any chatbot's agent calendar (superuser-gated).

Provides both a standard FastAPI HTTP route and an RPC handler
(for WebSocket-based requests via the unified events channel).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from airunner_services.api.routes.events import _rpc_register
from airunner_services.database.session import session_scope
from projects.uwuchat.server.models.calendar_event import CalendarEvent

router = APIRouter()


def _resolve_superuser_dep():
    """Return a dependency that requires superuser or loopback."""
    # nosemgrep: auth-import-error-fallback (see round-7 review)
    try:
        from extensions.auth.server.dependencies import (
            require_superuser,
        )

        return require_superuser
    except ImportError:
        pass

    async def _loopback_only(request) -> int:
        from airunner_services.api.server import (
            is_loopback_request,
        )

        if not is_loopback_request(request):
            raise HTTPException(
                status_code=403, detail="Admin access required",
            )
        return 0

    return _loopback_only


_superuser_dep = _resolve_superuser_dep()


@router.get("/chatbots/{chatbot_id}/calendar")
async def admin_chatbot_calendar(
    chatbot_id: int,
    year: int = Query(..., description="Year (e.g. 2026)"),
    month: int = Query(..., ge=1, le=12, description="Month 1-12"),
    include_deleted: bool = Query(
        False,
        description="Include soft-deleted events for debugging",
    ),
    _account_id: int = Depends(_superuser_dep),
) -> dict:
    """Return a chatbot's calendar events for a given month.

    Superuser-gated.  Includes ``is_recurring_reminder`` and
    ``recurrence_days`` fields so the admin viewer can distinguish
    recurring reminders from one-off events.
    """
    import datetime

    try:
        start_dt = datetime.datetime(
            year, month, 1, tzinfo=datetime.timezone.utc,
        )
        if month == 12:
            end_dt = datetime.datetime(
                year + 1, 1, 1, tzinfo=datetime.timezone.utc,
            )
        else:
            end_dt = datetime.datetime(
                year, month + 1, 1, tzinfo=datetime.timezone.utc,
            )
    except ValueError as exc:
        raise HTTPException(400, f"Invalid year/month: {exc}")

    filters = [
        CalendarEvent.chatbot_id == chatbot_id,
        CalendarEvent.starts_at >= start_dt,
        CalendarEvent.starts_at < end_dt,
    ]
    if not include_deleted:
        filters.append(CalendarEvent.deleted.is_(False))

    with session_scope() as session:
        rows = (
            session.query(CalendarEvent)
            .filter(*filters)
            .order_by(CalendarEvent.starts_at.asc())
            .all()
        )
        events = [
            {
                "id": r.id,
                "title": r.title,
                "description": r.description,
                "starts_at": (
                    r.starts_at.isoformat()
                    if getattr(r, "starts_at", None) else ""
                ),
                "ends_at": (
                    r.ends_at.isoformat()
                    if getattr(r, "ends_at", None) else None
                ),
                "all_day": r.all_day,
                "is_recurring_reminder": getattr(
                    r, "is_recurring_reminder", False,
                ),
                "recurrence_days": getattr(
                    r, "recurrence_days", None,
                ),
                "deleted": getattr(r, "deleted", False),
            }
            for r in rows
        ]

    return {
        "chatbot_id": chatbot_id,
        "year": year,
        "month": month,
        "events": events,
    }


# ── RPC handler (for WebSocket-based requests via the unified
#    events channel) ────────────────────────────────────────────


def _require_superuser_rpc(ws: Any) -> int | None:
    """Return account_id if the WebSocket user is a superuser."""
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


@_rpc_register("GET", "/api/v1/admin/chatbots/{chatbot_id}/calendar")
async def _rpc_admin_chatbot_calendar(
    body: dict, path_params: dict, ws: Any, **kw: Any,
) -> dict[str, Any]:
    """RPC handler: return a chatbot's calendar events for a month."""
    account_id = _require_superuser_rpc(ws)
    if account_id is None:
        return {
            "status": 403,
            "body": {"error": "Superuser required"},
        }

    import datetime

    try:
        chatbot_id = int(path_params["chatbot_id"])
        year = int(body.get("year", ""))
        month = int(body.get("month", ""))
        include_deleted = str(body.get("include_deleted", "")).lower() == "true"
    except (ValueError, KeyError, TypeError) as exc:
        return {
            "status": 400,
            "body": {"error": f"Invalid parameters: {exc}"},
        }

    try:
        start_dt = datetime.datetime(
            year, month, 1, tzinfo=datetime.timezone.utc,
        )
        if month == 12:
            end_dt = datetime.datetime(
                year + 1, 1, 1, tzinfo=datetime.timezone.utc,
            )
        else:
            end_dt = datetime.datetime(
                year, month + 1, 1, tzinfo=datetime.timezone.utc,
            )
    except ValueError as exc:
        return {
            "status": 400,
            "body": {"error": f"Invalid year/month: {exc}"},
        }

    filters = [
        CalendarEvent.chatbot_id == chatbot_id,
        CalendarEvent.starts_at >= start_dt,
        CalendarEvent.starts_at < end_dt,
    ]
    if not include_deleted:
        filters.append(CalendarEvent.deleted.is_(False))

    with session_scope() as session:
        rows = (
            session.query(CalendarEvent)
            .filter(*filters)
            .order_by(CalendarEvent.starts_at.asc())
            .all()
        )
        events = [
            {
                "id": r.id,
                "title": r.title,
                "description": r.description,
                "starts_at": (
                    r.starts_at.isoformat()
                    if getattr(r, "starts_at", None) else ""
                ),
                "ends_at": (
                    r.ends_at.isoformat()
                    if getattr(r, "ends_at", None) else None
                ),
                "all_day": r.all_day,
                "is_recurring_reminder": getattr(
                    r, "is_recurring_reminder", False,
                ),
                "recurrence_days": getattr(
                    r, "recurrence_days", None,
                ),
                "deleted": getattr(r, "deleted", False),
            }
            for r in rows
        ]

    return {
        "status": 200,
        "body": {
            "chatbot_id": chatbot_id,
            "year": year,
            "month": month,
            "events": events,
        },
    }
