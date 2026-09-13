"""Lifecycle states for managed models."""

from enum import Enum


class ModelStatus(Enum):
    """Lifecycle states for managed models."""

    UNLOADED = "Unloaded"
    LOADED = "Loaded"
    READY = "Ready"
    LOADING = "Loading"
    UNLOADING = "Unloading"
    FAILED = "Failed"
