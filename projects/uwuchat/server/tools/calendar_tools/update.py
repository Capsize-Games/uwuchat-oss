"""LLM tool: update_calendar_event — modify an existing calendar entry."""

from __future__ import annotations

import datetime
import logging
from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import ToolCategory, tool
from projects.uwuchat.server.tools.calendar_tools._helpers import (
    parse_datetime,
)

logger = logging.getLogger(__name__)


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
    name="update_calendar_event",
    category=ToolCategory.SYSTEM,
    description=(
        "Update an existing calendar event. Use this when the user "
        "wants to reschedule, rename, or change details of an event. "
        "Search by title substring — if multiple events match, the "
        "tool will tell you so you can ask the user to clarify which "
        "one they meant."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=[
        "update event", "reschedule", "move event", "change event",
        "postpone", "calendar update",
    ],
    input_examples=[
        {
            "title_substring": "dentist",
            "new_title": "Call dentist (new location)",
            "new_starts_at": "2026-07-10T15:00:00-06:00",
        },
    ],
)
def update_calendar_event(
    title_substring: Annotated[
        str,
        "Part of the event title to search for "
        "(e.g. 'dentist' finds 'Call dentist').",
    ],
    new_title: Annotated[
        str | None,
        "New title for the event, if changing it.",
    ] = None,
    new_starts_at: Annotated[
        str | None,
        "New start datetime in ISO-8601 with timezone "
        "(e.g. '2026-07-10T15:00:00-06:00').",
    ] = None,
    new_ends_at: Annotated[
        str | None,
        "New end datetime in ISO-8601 with timezone.",
    ] = None,
    new_description: Annotated[
        str | None,
        "Updated description or notes.",
    ] = None,
    rough_date: Annotated[
        str | None,
        "Rough date to help narrow the search "
        "(e.g. '2026-07-10' or 'next Thursday'). "
        "If you know roughly when the event is, "
        "provide this to avoid mismatches.",
    ] = None,
    agent: Any = None,
) -> str:
    """Find and update a calendar event by fuzzy title match."""
    user = getattr(agent, "user", None) if agent else None
    chatbot = getattr(agent, "chatbot", None) if agent else None
    user_id = getattr(user, "id", None) if user else None
    chatbot_id = getattr(chatbot, "id", None) if chatbot else None
    if not user_id or not chatbot_id:
        return "I couldn't update that event — session issue."

    omnipotent = bool(
        chatbot
        and getattr(chatbot, "is_system_bot", False)
        and getattr(chatbot, "omnipotent_knowledge", False)
    )

    date_start = None
    date_end = None
    if rough_date:
        try:
            rough_dt = parse_datetime(rough_date)
            date_start = rough_dt.replace(
                hour=0, minute=0, second=0, microsecond=0,
            )
            date_end = date_start + datetime.timedelta(days=1)
        except (ValueError, TypeError):
            # Try parsing as date-only string
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

    changed = []
    if new_title is not None:
        event.title = new_title.strip()
        changed.append("title")
    if new_starts_at is not None:
        try:
            event.starts_at = parse_datetime(new_starts_at)
            changed.append("start time")
        except (ValueError, TypeError) as exc:
            logging.warning(
                "Invalid new_starts_at: %s — %s", new_starts_at, exc,
            )
            return "I had trouble understanding that new date/time."
    if new_ends_at is not None:
        try:
            event.ends_at = parse_datetime(new_ends_at)
            changed.append("end time")
        except (ValueError, TypeError) as exc:
            logging.warning(
                "Invalid new_ends_at: %s — %s", new_ends_at, exc,
            )
    if new_description is not None:
        event.description = new_description.strip()
        changed.append("description")

    if not changed:
        return (
            f"Event '{event.title}' wasn't changed — no new values "
            "were provided."
        )

    event.save()
    return (
        f"Updated {', '.join(changed)} for '{event.title}'. "
        "Let the user know in your voice what was changed."
    )
