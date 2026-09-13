"""Shared helpers for calendar tool modules."""

from __future__ import annotations

import datetime


def parse_datetime(value: str) -> datetime.datetime:
    """Parse an ISO-8601 datetime string, defaulting to UTC if no tz."""
    dt = datetime.datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def format_event_time(dt: datetime.datetime) -> str:
    """Return a friendly time string: '9am', '12:30pm'."""
    hour = dt.hour
    minute = dt.minute
    ampm = "am" if hour < 12 else "pm"
    display_hour = hour if hour != 0 else 12
    if display_hour > 12:
        display_hour -= 12
    if minute == 0:
        return f"{display_hour}{ampm}"
    return f"{display_hour}:{minute:02d}{ampm}"
