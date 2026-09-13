"""Parse relative-date language in a user message into a UTC date range.

Used to turn questions like "what did we talk about yesterday" into an
actual [start, end) filter over ConversationTurn.created_at, instead of
treating the words as just more text to embed and match semantically.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

_DATE_PHRASES: tuple[str, ...] = (
    "yesterday",
    "last night",
    "today",
    "this morning",
    "this week",
    "last week",
)
_DAY_NAMES = tuple(_WEEKDAYS.keys())


def _is_date_query(text: str) -> bool:
    """Return True if ``text`` contains a relative-date phrase."""
    lower = text.lower()
    if any(p in lower for p in _DATE_PHRASES):
        return True
    if any(d in lower for d in _DAY_NAMES):
        return True
    if re.search(r"\d+\s+days?\s+ago", lower):
        return True
    if "earlier" in lower and "today" in lower:
        return True
    return False


def parse_relative_date_range(
    query: str,
    reference_dt: datetime,
) -> Optional[Tuple[datetime, datetime]]:
    """Return a (start, end) naive-UTC datetime range for a relative-date
    phrase found in ``query``, or ``None`` if no date phrase is found.

    ``reference_dt`` must be timezone-aware and represents "now" in the
    timezone the phrase should be evaluated in (typically the user's
    local time — see ``resolve_reference_datetime`` below).

    The returned range is naive UTC so it can be compared directly
    against ``ConversationTurn.created_at`` (stored as naive UTC).
    """
    text = query.lower()
    local_midnight = reference_dt.replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    result: Optional[Tuple[datetime, datetime]] = None

    if "yesterday" in text or "last night" in text:
        start = local_midnight - timedelta(days=1)
        result = (start, local_midnight)

    elif "today" in text or "this morning" in text or (
        "earlier" in text and "today" in text
    ):
        result = (local_midnight, local_midnight + timedelta(days=1))

    elif "this week" in text:
        start = local_midnight - timedelta(
            days=local_midnight.weekday()
        )
        result = (start, local_midnight + timedelta(days=1))

    elif "last week" in text:
        this_week_start = local_midnight - timedelta(
            days=local_midnight.weekday()
        )
        result = (
            this_week_start - timedelta(days=7),
            this_week_start,
        )

    else:
        for name, idx in _WEEKDAYS.items():
            if name in text:
                days_back = (
                    local_midnight.weekday() - idx
                ) % 7
                # "monday" alone → most recent past Monday;
                # "last monday" means the same thing in ordinary
                # English, so no extra adjustment.
                days_back = days_back or 7
                start = local_midnight - timedelta(days=days_back)
                result = (start, start + timedelta(days=1))
                break

        if result is None:
            match = re.search(r"(\d+)\s+days?\s+ago", text)
            if match:
                n = int(match.group(1))
                start = local_midnight - timedelta(days=n)
                result = (start, start + timedelta(days=1))

    if result is None:
        return None

    # Convert to naive UTC so filters match ConversationTurn.created_at
    # (stored as naive UTC via datetime.utcnow).
    start_utc = result[0].astimezone(timezone.utc).replace(
        tzinfo=None
    )
    end_utc = result[1].astimezone(timezone.utc).replace(
        tzinfo=None
    )
    return start_utc, end_utc


def resolve_reference_datetime(chatbot) -> datetime:
    """Return the tz-aware 'now' to evaluate relative-date phrases against.

    Mirrors the timezone-resolution order already used by
    ``per_turn_context.py:_datetime_part`` (chatbot location timezone,
    else UTC) so "yesterday" means the same thing everywhere in the
    prompt pipeline.
    """
    location = getattr(chatbot, "location", None) or {}
    tz_name = location.get("timezone") if location else None
    if tz_name:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz_name))
    return datetime.now(timezone.utc)
