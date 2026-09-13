"""LLM tool: delete_calendar_event — cancel a calendar entry."""

from __future__ import annotations

import datetime
from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import ToolCategory, tool


def _resolve_event(
    user_id: int,
    chatbot_id: int,
    omnipotent: bool,
    title_substring: str,
    date_window_start: datetime.datetime | None,
    date_window_end: datetime.datetime | None,
) -> tuple:
    """Find a calendar event by fuzzy title + optional date window.

    Returns ``(event, message)`` where exactly one is not None.
    """
    from projects.uwuchat.server.models.calendar_event import CalendarEvent

    filters = [
        CalendarEvent.user_id == user_id,
        CalendarEvent.title.ilike(f"%{title_substring}%"),
        CalendarEvent.deleted.is_(False),
    ]
    if not omnipotent:
        filters.append(CalendarEvent.chatbot_id == chatbot_id)

    if date_window_start is not None and date_window_end is not None:
        filters.append(CalendarEvent.starts_at >= date_window_start)
        filters.append(CalendarEvent.starts_at < date_window_end)

    matches = (
        CalendarEvent.objects.query()
        .filter(*filters)
        .order_by(CalendarEvent.starts_at.asc())
        .limit(5)
        .all()
    )

    if not matches:
        return (None, f"No event matching '{title_substring}' found.")
    if len(matches) > 1:
        lines = [f"Multiple events match '{title_substring}':"]
        for ev in matches:
            label = ev.starts_at.strftime("%a %b %-d")
            lines.append(f"  - {ev.title} ({label})")
        lines.append("Ask the user which one they meant.")
        return (None, "\n".join(lines))

    return (matches[0], None)


@tool(
    name="delete_calendar_event",
    category=ToolCategory.SYSTEM,
    description=(
        "Cancel/delete a calendar event (soft-delete — it can be "
        "recovered if needed). Use this when the user wants to cancel "
        "an appointment, meeting, or any calendar entry. Search by "
        "title substring."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=[
        "cancel event", "delete event", "remove event",
        "cancel appointment", "cancel meeting",
    ],
    input_examples=[
        {
            "title_substring": "dentist",
            "rough_date": "2026-07-03",
        },
    ],
)
def delete_calendar_event(
    title_substring: Annotated[
        str,
        "Part of the event title to search for "
        "(e.g. 'dentist' finds 'Call dentist').",
    ],
    rough_date: Annotated[
        str | None,
        "Rough date to help narrow the search "
        "(e.g. '2026-07-10' or 'next Thursday').",
    ] = None,
    agent: Any = None,
) -> str:
    """Soft-delete a calendar event by fuzzy title match."""
    user = getattr(agent, "user", None) if agent else None
    chatbot = getattr(agent, "chatbot", None) if agent else None
    user_id = getattr(user, "id", None) if user else None
    chatbot_id = getattr(chatbot, "id", None) if chatbot else None
    if not user_id or not chatbot_id:
        return "I couldn't cancel that event — session issue."

    omnipotent = bool(
        chatbot
        and getattr(chatbot, "is_system_bot", False)
        and getattr(chatbot, "omnipotent_knowledge", False)
    )

    date_start = None
    date_end = None
    if rough_date:
        from projects.uwuchat.server.tools.calendar_tools._helpers import (
            parse_datetime,
        )

        try:
            rough_dt = parse_datetime(rough_date)
            date_start = rough_dt.replace(
                hour=0, minute=0, second=0, microsecond=0,
            )
            date_end = date_start + datetime.timedelta(days=1)
        except (ValueError, TypeError):
            try:
                d = datetime.date.fromisoformat(rough_date)
                date_start = datetime.datetime(
                    d.year, d.month, d.day,
                    tzinfo=datetime.timezone.utc,
                )
                date_end = date_start + datetime.timedelta(days=1)
            except (ValueError, TypeError):
                pass

    event, msg = _resolve_event(
        user_id, chatbot_id, omnipotent,
        title_substring, date_start, date_end,
    )
    if msg:
        return msg

    event.delete()
    return (
        f"Cancelled event '{event.title}'. Let the user know in your "
        "voice that it's been removed from the calendar."
    )
