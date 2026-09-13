"""Runtime execution mode enum."""

from enum import Enum


class RuntimeMode(str, Enum):
    """Execution mode used by a runtime."""

    LOCAL_FALLBACK = "local_fallback"
    IN_PROCESS = "in_process"
