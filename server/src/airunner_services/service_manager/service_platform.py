"""Supported platforms for service installation."""

from enum import Enum


class ServicePlatform(Enum):
    """Supported platforms for service installation."""

    LINUX = "linux"
    MACOS = "macos"
    WINDOWS = "windows"
    UNKNOWN = "unknown"
