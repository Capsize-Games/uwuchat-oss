"""LLM tool: add_calendar_event — create a calendar entry."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import ToolCategory, tool
from projects.uwuchat.server.tools.calendar_tools._helpers import (
    parse_datetime,
    format_event_time,
)


@tool(
    name="add_calendar_event",
    category=ToolCategory.SYSTEM,
    description=(
        "Add an event to the user's personal calendar. "
        "Call this when the user mentions a plan, appointment, "
        "deadline, or anything with a date/time — BUT only if you "
        "already have enough information (title + date/time). "
        "If the user is vague ('a dentist appointment coming up'), "
        "ask a follow-up question first — do not guess dates."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=[
        "calendar", "event", "appointment", "reminder", "schedule",
        "plan", "meeting", "dinner", "call", "deadline",
    ],
    input_examples=[
        {
            "title": "Call dentist",
            "starts_at": "2026-07-03T14:00:00-06:00",
            "reminder_minutes": 30,
        },
        {
            "title": "Lunch with a friend",
            "starts_at": "2026-06-30T12:30:00-06:00",
            "ends_at": "2026-06-30T13:30:00-06:00",
            "description": "That new ramen place downtown",
        },
    ],
)
def add_calendar_event(
    title: Annotated[
        str,
        "Short title for the event (e.g. 'Dentist appointment').",
    ],
    starts_at: Annotated[
        str,
        "ISO-8601 datetime with timezone offset when the event "
        "starts (e.g. '2026-07-03T14:00:00-06:00').",
    ],
    ends_at: Annotated[
        str | None,
        "ISO-8601 datetime when the event ends. Optional — leave "
        "empty for point-in-time events.",
    ] = None,
    all_day: Annotated[
        bool,
        "True if this is an all-day event (birthdays, holidays).",
    ] = False,
    description: Annotated[
        str | None,
        "Optional longer description or notes about the event.",
    ] = None,
    reminder_minutes: Annotated[
        int | None,
        "Minutes before the event to remind the user. "
        "Common values: 10, 30, 60, 1440 (1 day).",
    ] = None,
    agent: Any = None,
) -> str:
    """Persist a calendar event and return a confirmation message."""
    user = getattr(agent, "user", None) if agent else None
    chatbot = getattr(agent, "chatbot", None) if agent else None
    user_id = getattr(user, "id", None) if user else None
    chatbot_id = getattr(chatbot, "id", None) if chatbot else None
    if not user_id or not chatbot_id:
        return (
            "I couldn't save that to your calendar — something's "
            "off with my session. Can we try again?"
        )

    try:
        starts_dt = parse_datetime(starts_at)
    except (ValueError, TypeError) as exc:
        logging.warning("Invalid starts_at: %s — %s", starts_at, exc)
        return (
            "I had trouble understanding that date/time. "
            "Could you say it again differently?"
        )

    ends_dt = None
    if ends_at:
        try:
            ends_dt = parse_datetime(ends_at)
        except (ValueError, TypeError) as exc:
            logging.warning("Invalid ends_at: %s — %s", ends_at, exc)
            ends_dt = None

    from projects.uwuchat.server.models.calendar_event import CalendarEvent

    CalendarEvent.objects.create(
        user_id=user_id,
        chatbot_id=chatbot_id,
        title=title.strip(),
        description=description.strip() if description else None,
        starts_at=starts_dt,
        ends_at=ends_dt,
        all_day=all_day,
        reminder_minutes=reminder_minutes,
    )

    date_label = starts_dt.strftime("%A, %B %-d")
    time_label = format_event_time(starts_dt)
    suffix = ""
    if all_day:
        suffix = " (all day)"
    elif ends_dt:
        suffix = f" until {format_event_time(ends_dt)}"

    return (
        f"Event '{title}' added to the calendar for {date_label} "
        f"at {time_label}{suffix}. Let the user know in your voice "
        f"that it's on the calendar."
    )
