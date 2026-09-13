"""Base class for platform-specific service handlers."""

from pathlib import Path
from typing import Any

from airunner_services.service_manager.service_state import ServiceState


class ServiceHandlerBase:
    """Base class for platform-specific service handlers."""

    def __init__(self):
        from airunner_services.settings import AIRUNNER_LOG_LEVEL

        from airunner_services.utils.application import get_logger

        self.logger = get_logger(
            self.__class__.__name__, AIRUNNER_LOG_LEVEL
        )

    def install(self, config_path: Path, **kwargs: Any) -> bool:
        """Install service on this platform."""
        raise NotImplementedError

    def uninstall(self) -> bool:
        """Uninstall service from this platform."""
        raise NotImplementedError

    def start(self) -> bool:
        """Start the service."""
        raise NotImplementedError

    def stop(self) -> bool:
        """Stop the service."""
        raise NotImplementedError

    def status(self) -> ServiceState:
        """Get service status."""
        raise NotImplementedError

    def is_installed(self) -> bool:
        """Check if service is installed."""
        raise NotImplementedError
