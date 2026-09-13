"""Status of a long-running project."""

from enum import Enum


class ProjectStatus(str, Enum):
    """Status of a long-running project."""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
