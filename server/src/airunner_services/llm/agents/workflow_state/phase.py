"""Standard phases that workflows can use."""

from enum import Enum


class Phase(Enum):
    """Standard phases that workflows can use."""

    DISCOVERY = "discovery"
    PLANNING = "planning"
    EXECUTION = "execution"
    REVIEW = "review"
    COMPLETE = "complete"
