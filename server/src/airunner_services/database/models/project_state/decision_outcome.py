"""Outcome of a past decision."""

from enum import Enum


class DecisionOutcome(str, Enum):
    """Outcome of a past decision."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    REVERTED = "reverted"
