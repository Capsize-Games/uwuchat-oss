"""Calendar tools — create, update, delete, and list calendar events.

Importing this package triggers tool registration via the @tool decorators.
"""

from projects.uwuchat.server.tools.calendar_tools.add import (
    add_calendar_event,
)
from projects.uwuchat.server.tools.calendar_tools.update import (
    update_calendar_event,
)
from projects.uwuchat.server.tools.calendar_tools.delete import (
    delete_calendar_event,
)
from projects.uwuchat.server.tools.calendar_tools.list import (
    list_calendar_events,
)
from projects.uwuchat.server.tools.calendar_tools.recurring import (
    add_recurring_reminder,
)

__all__ = [
    "add_calendar_event",
    "update_calendar_event",
    "delete_calendar_event",
    "list_calendar_events",
    "add_recurring_reminder",
]
