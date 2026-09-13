"""LLM tool: list_calendar_events — query calendar entries."""

from __future__ import annotations

import datetime
from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import ToolCategory, tool
from projects.uwuchat.server.tools.calendar_tools._helpers import (
    format_event_time,
)


@tool(
    name="list_calendar_events",
    category=ToolCategory.SYSTEM,
    description=(
        "List events on the user's calendar. Use this when the user "
        "asks what's on their schedule ('what do I have this week', "
        "'am I free Thursday', 'what's on my calendar'). "
        "Returns a natural-language summary of matching events."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=[
        "list events", "what's on my calendar", "schedule",
        "what do I have", "am I free", "my calendar",
    ],
    input_examples=[
        {"days": "7"},
        {"days": "1", "query": "dentist"},
    ],
)
def list_calendar_events(
    days: Annotated[
        int,
        "Number of days to look ahead (default 7, i.e. one week).",
    ] = 7,
    query: Annotated[
        str | None,
        "Optional title substring to filter by "
        "(e.g. 'dentist' to find specific events).",
    ] = None,
    agent: Any = None,
) -> str:
    """Return a natural-language summary of upcoming calendar events."""
    user = getattr(agent, "user", None) if agent else None
    chatbot = getattr(agent, "chatbot", None) if agent else None
    user_id = getattr(user, "id", None) if user else None
    chatbot_id = getattr(chatbot, "id", None) if chatbot else None
    if not user_id or not chatbot_id:
        return "I couldn't look up your calendar — session issue."

    omnipotent = bool(
        chatbot
        and getattr(chatbot, "is_system_bot", False)
        and getattr(chatbot, "omnipotent_knowledge", False)
    )

    from projects.uwuchat.server.models.calendar_event import CalendarEvent

    now = datetime.datetime.now(datetime.timezone.utc)
    day_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = day_end + datetime.timedelta(days=max(days, 1))

    filters = [
        CalendarEvent.user_id == user_id,
        CalendarEvent.starts_at >= day_end,
        CalendarEvent.starts_at < window_end,
        CalendarEvent.deleted.is_(False),
    ]
    if not omnipotent:
        filters.append(CalendarEvent.chatbot_id == chatbot_id)

    if query:
        filters.append(CalendarEvent.title.ilike(f"%{query}%"))

    rows = (
        CalendarEvent.objects.query(
            CalendarEvent.title,
            CalendarEvent.starts_at,
            CalendarEvent.ends_at,
            CalendarEvent.all_day,
        )
        .filter(*filters)
        .order_by(CalendarEvent.starts_at.asc())
        .limit(20)
        .all()
    )

    if not rows:
        scope = f"the next {days} day(s)"
        if query:
            return (
                f"No events matching '{query}' found in {scope}."
            )
        return (
            f"No events on the calendar for {scope}. Tell the user "
            "their schedule is clear."
        )

    lines = [f"Calendar for the next {days} day(s):"]
    for title, starts, ends, all_day in rows:
        date_label = starts.strftime("%A, %b %-d")
        if all_day:
            lines.append(f"- {date_label}: {title} (all day)")
        elif ends:
            lines.append(
                f"- {date_label}: {title} "
                f"{format_event_time(starts)} — "
                f"{format_event_time(ends)}"
            )
        else:
            lines.append(
                f"- {date_label}: {title} at "
                f"{format_event_time(starts)}"
            )

    return (
        "\n".join(lines) + "\n\nRelay this to the user in your voice."
    )
