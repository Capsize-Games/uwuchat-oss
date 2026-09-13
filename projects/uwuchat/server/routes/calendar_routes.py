"""Calendar REST API — CRUD for the client panel."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from airunner_services.database.session import session_scope
from extensions.auth.server.dependencies import require_auth
from projects.uwuchat.server.models.calendar_event import CalendarEvent

router = APIRouter()


class CalendarEventOut(BaseModel):
    """Serialised calendar event for the client."""
    id: int
    title: str
    description: Optional[str]
    starts_at: str
    ends_at: Optional[str]
    all_day: bool
    reminder_minutes: Optional[int]
    chatbot_id: Optional[int]

    class Config:
        from_attributes = True


class CalendarListOut(BaseModel):
    """List of calendar events for a date range."""
    events: list[CalendarEventOut]


def _is_omnipotent(chatbot_id: int | None) -> bool:
    """Return True if the given chatbot has omnipotent knowledge."""
    if chatbot_id is None:
        return False
    try:
        from airunner_services.database.models.chatbot import Chatbot

        chatbot = Chatbot.objects.get(chatbot_id)
        if chatbot is None:
            return False
        return bool(
            getattr(chatbot, "is_system_bot", False)
            and getattr(chatbot, "omnipotent_knowledge", False)
        )
    except Exception:
        return False


@router.get("/", response_model=CalendarListOut)
async def list_calendar_events(
    from_date: str = Query(
        ...,
        description="ISO date string for range start",
    ),
    to_date: str = Query(
        ...,
        description="ISO date string for range end (exclusive)",
    ),
    chatbot_id: Optional[int] = Query(
        None,
        description="Scope events to this chatbot",
    ),
    account_id: int = Depends(require_auth),
) -> CalendarListOut:
    """Return calendar events in the given date range.

    When *chatbot_id* is provided, events are scoped to that chatbot
    unless the chatbot has ``omnipotent_knowledge`` enabled, in which
    case all of the user's events are returned.
    """
    import datetime

    try:
        start = datetime.date.fromisoformat(from_date)
        end = datetime.date.fromisoformat(to_date)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid date format: {exc}")

    start_dt = datetime.datetime(
        start.year, start.month, start.day,
        tzinfo=datetime.timezone.utc,
    )
    end_dt = datetime.datetime(
        end.year, end.month, end.day,
        tzinfo=datetime.timezone.utc,
    )

    filters = [
        CalendarEvent.user_id == account_id,
        CalendarEvent.starts_at >= start_dt,
        CalendarEvent.starts_at < end_dt,
        CalendarEvent.deleted.is_(False),
    ]
    if chatbot_id is not None and not _is_omnipotent(chatbot_id):
        filters.append(CalendarEvent.chatbot_id == chatbot_id)

    with session_scope() as session:
        rows = (
            session.query(CalendarEvent)
            .filter(*filters)
            .order_by(CalendarEvent.starts_at.asc())
            .all()
        )
        # Serialize while the session is still open -- session_scope()
        # closes the session on exit (expire_on_commit is the SQLAlchemy
        # default), so building CalendarEventOut after the `with` block
        # raised DetachedInstanceError on attribute access.
        events = [_to_out(r) for r in rows]
    return CalendarListOut(events=events)


def _to_out(row: CalendarEvent) -> CalendarEventOut:
    """Map an ORM row to the output schema."""
    return CalendarEventOut(
        id=row.id,
        title=row.title,
        description=row.description,
        starts_at=(
            row.starts_at.isoformat()
            if getattr(row, "starts_at", None) else ""
        ),
        ends_at=(
            row.ends_at.isoformat()
            if getattr(row, "ends_at", None) else None
        ),
        all_day=row.all_day,
        reminder_minutes=row.reminder_minutes,
        chatbot_id=getattr(row, "chatbot_id", None),
    )
