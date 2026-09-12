"""Runtime action enum."""

from enum import Enum


class RuntimeAction(str, Enum):
    """Actions supported by the daemon and runtime boundary."""

    HEALTH = "health"
    LOAD_MODEL = "load_model"
    UNLOAD_MODEL = "unload_model"
    INVOKE = "invoke"
    CANCEL = "cancel"
    STATUS = "status"
