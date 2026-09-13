"""Service states."""

from enum import Enum


class ServiceState(Enum):
    """Service states."""

    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    UNKNOWN = "unknown"
