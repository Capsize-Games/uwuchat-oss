"""Status of a project feature."""

from enum import Enum


class FeatureStatus(str, Enum):
    """Status of a project feature."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    FAILING = "failing"
    PASSING = "passing"
    BLOCKED = "blocked"
