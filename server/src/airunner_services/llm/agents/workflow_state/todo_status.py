"""Status of a TODO item."""

from enum import Enum


class TodoStatus(Enum):
    """Status of a TODO item."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    SKIPPED = "skipped"
