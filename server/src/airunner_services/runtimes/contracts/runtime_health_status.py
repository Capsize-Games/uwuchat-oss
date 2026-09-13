"""Runtime health status enum."""

from enum import Enum


class RuntimeHealthStatus(str, Enum):
    """Health status reported by a runtime client."""

    UNKNOWN = "unknown"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"
