"""LLM tool: add_recurring_reminder — plan-based daily reminders."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import ToolCategory, tool

logger = logging.getLogger(__name__)

_VALID_DAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}


def _normalize_reminder_time(time_str: str | None) -> str | None:
    """Return a normalized ISO-8601 datetime string for the time only.

    Accepts flexible formats like '8am', '08:00', '20:00'.
    Returns None if parsing fails.
    """
    if not time_str:
        return None
    import datetime

    time_str = time_str.strip().lower()
    # Try "8am" / "8:30pm" format
    for fmt in ("%I%p", "%I:%M%p", "%H:%M", "%H"):
        try:
            parsed = datetime.datetime.strptime(
                time_str.replace(" ", ""), fmt,
            )
            return parsed.strftime("%H:%M")
        except ValueError:
            continue
    return None


@tool(
    name="add_recurring_reminder",
    category=ToolCategory.SYSTEM,
    description=(
        "Add a recurring daily reminder for the user. Use this when "
        "the user wants to be reminded of something every day or on "
        "specific days of the week — e.g. 'remind me to take my "
        "vitamins every morning', 'I want to work out Mon/Wed/Fri'. "
        "This creates a standing instruction that surfaces in context "
        "on matching days. Do NOT use this for one-off appointments."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=[
        "recurring reminder", "daily reminder", "every day",
        "every morning", "every evening", "workout reminder",
        "weekly reminder", "take my", "remind me to",
    ],
    input_examples=[
        {
            "title": "Take vitamins",
            "recurrence_days": "MON,TUE,WED,THU,FRI",
            "reminder_time": "8am",
            "description": "Vitamin D and magnesium with breakfast",
        },
        {
            "title": "Workout",
            "recurrence_days": "MON,WED,FRI",
            "reminder_time": "7am",
        },
    ],
)
def add_recurring_reminder(
    title: Annotated[
        str,
        "Short title (e.g. 'Take vitamins', 'Workout').",
    ],
    recurrence_days: Annotated[
        str,
        "Comma-separated day codes: MON,TUE,WED,THU,FRI,SAT,SUN. "
        "E.g. 'MON,WED,FRI' for alternate days or "
        "'MON,TUE,WED,THU,FRI' for weekdays.",
    ],
    reminder_time: Annotated[
        str,
        "Time of day for the reminder (e.g. '8am', '7:00am', '20:00').",
    ],
    description: Annotated[
        str | None,
        "Optional notes (e.g. specific dosage, workout details).",
    ] = None,
    agent: Any = None,
) -> str:
    """Create a recurring reminder as a CalendarEvent row."""
    user = getattr(agent, "user", None) if agent else None
    chatbot = getattr(agent, "chatbot", None) if agent else None
    user_id = getattr(user, "id", None) if user else None
    chatbot_id = getattr(chatbot, "id", None) if chatbot else None
    if not user_id or not chatbot_id:
        return (
            "I couldn't save that reminder — session issue."
        )

    # Validate recurrence_days
    raw_days = [
        d.strip().upper() for d in recurrence_days.split(",")
    ]
    valid_days = [d for d in raw_days if d in _VALID_DAYS]
    invalid = [d for d in raw_days if d not in _VALID_DAYS]
    if invalid:
        return (
            f"Invalid day codes: {', '.join(invalid)}. "
            f"Use MON,TUE,WED,THU,FRI,SAT,SUN."
        )
    if not valid_days:
        return "At least one valid day code is required."

    normalized_days = ",".join(valid_days)

    # Use a fixed reference date — time component only matters here
    import datetime

    ref_date = datetime.date(2000, 1, 3)  # A Monday
    time_norm = _normalize_reminder_time(reminder_time)
    if time_norm is None:
        return (
            "I had trouble understanding that time. "
            "Try something like '8am', '7:00am', or '20:00'."
        )

    hour, minute = time_norm.split(":")
    starts_dt = datetime.datetime(
        ref_date.year, ref_date.month, ref_date.day,
        int(hour), int(minute),
        tzinfo=datetime.timezone.utc,
    )

    from projects.uwuchat.server.models.calendar_event import CalendarEvent

    CalendarEvent.objects.create(
        user_id=user_id,
        chatbot_id=chatbot_id,
        title=title.strip(),
        description=description.strip() if description else None,
        starts_at=starts_dt,
        is_recurring_reminder=True,
        recurrence_days=normalized_days,
    )

    human_days = _day_codes_to_human(valid_days)
    return (
        f"Recurring reminder '{title}' set for {human_days} "
        f"at {time_norm}. Let the user know in your voice "
        "that it's set up."
    )


def _day_codes_to_human(codes: list[str]) -> str:
    """Convert ['MON','WED','FRI'] to 'Mon, Wed, Fri'."""
    mapping = {
        "MON": "Mon", "TUE": "Tue", "WED": "Wed",
        "THU": "Thu", "FRI": "Fri", "SAT": "Sat", "SUN": "Sun",
    }
    return ", ".join(mapping.get(c, c) for c in codes)
