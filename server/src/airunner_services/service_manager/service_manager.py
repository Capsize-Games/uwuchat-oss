"""The cross-platform service manager facade."""

import os
import platform
from pathlib import Path
from typing import Optional

from airunner_services.config.runtime_layout import (
    build_runtime_directory_layout,
)
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.service_manager.service_platform import (
    ServicePlatform,
)
from airunner_services.service_manager.service_state import ServiceState
from airunner_services.utils.application import get_logger

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)


class ServiceManager:
    """
    Manages AI Runner background service across platforms.

    Provides unified interface for:
    - Service installation/uninstallation
    - Service control (start, stop, restart)
    - Service status checking
    - Configuration management
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize service manager.

        Args:
            config_path: Path to daemon configuration file (daemon.yaml)
        """
        from airunner_services.service_manager.linux_systemd_handler import (
            LinuxSystemdHandler,
        )
        from airunner_services.service_manager.macos_launch_agent_handler import (
            MacOSLaunchAgentHandler,
        )
        from airunner_services.service_manager.windows_service_handler import (
            WindowsServiceHandler,
        )

        self.logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)
        self.platform = self._detect_platform()
        self.config_path = config_path or self._default_config_path()

        # Platform-specific handlers
        self._handlers = {
            ServicePlatform.LINUX: LinuxSystemdHandler(),
            ServicePlatform.MACOS: MacOSLaunchAgentHandler(),
            ServicePlatform.WINDOWS: WindowsServiceHandler(),
        }

    def _detect_platform(self) -> ServicePlatform:
        """Detect the current platform."""
        system = platform.system().lower()
        if system == "linux":
            return ServicePlatform.LINUX
        elif system == "darwin":
            return ServicePlatform.MACOS
        elif system == "windows":
            return ServicePlatform.WINDOWS
        else:
            self.logger.warning(f"Unknown platform: {system}")
            return ServicePlatform.UNKNOWN

    def _default_config_path(self) -> Path:
        """Get default configuration path."""
        if self.platform == ServicePlatform.WINDOWS:
            config_dir = Path(os.environ.get("APPDATA", "")) / "airunner"
            return config_dir / "daemon.yaml"
        layout = build_runtime_directory_layout()
        return layout.config_file("daemon")

    def install(self, **kwargs) -> bool:
        """
        Install AI Runner as a service.

        Args:
            **kwargs: Platform-specific installation options

        Returns:
            True if installation successful, False otherwise
        """
        if self.platform == ServicePlatform.UNKNOWN:
            self.logger.error("Cannot install service on unknown platform")
            return False

        handler = self._handlers.get(self.platform)
        if not handler:
            self.logger.error(f"No handler for platform: {self.platform}")
            return False

        try:
            return handler.install(self.config_path, **kwargs)
        except Exception as e:
            self.logger.error(f"Failed to install service: {e}")
            return False

    def uninstall(self) -> bool:
        """
        Uninstall AI Runner service.

        Returns:
            True if uninstallation successful, False otherwise
        """
        if self.platform == ServicePlatform.UNKNOWN:
            self.logger.error("Cannot uninstall service on unknown platform")
            return False

        handler = self._handlers.get(self.platform)
        if not handler:
            self.logger.error(f"No handler for platform: {self.platform}")
            return False

        try:
            # Stop service before uninstalling
            self.stop()
            return handler.uninstall()
        except Exception as e:
            self.logger.error(f"Failed to uninstall service: {e}")
            return False

    def start(self) -> bool:
        """
        Start the AI Runner service.

        Returns:
            True if service started successfully, False otherwise
        """
        handler = self._handlers.get(self.platform)
        if not handler:
            return False

        try:
            return handler.start()
        except Exception as e:
            self.logger.error(f"Failed to start service: {e}")
            return False

    def stop(self) -> bool:
        """
        Stop the AI Runner service.

        Returns:
            True if service stopped successfully, False otherwise
        """
        handler = self._handlers.get(self.platform)
        if not handler:
            return False

        try:
            return handler.stop()
        except Exception as e:
            self.logger.error(f"Failed to stop service: {e}")
            return False

    def restart(self) -> bool:
        """
        Restart the AI Runner service.

        Returns:
            True if service restarted successfully, False otherwise
        """
        return self.stop() and self.start()

    def status(self) -> ServiceState:
        """
        Check service status.

        Returns:
            Current service state
        """
        handler = self._handlers.get(self.platform)
        if not handler:
            return ServiceState.UNKNOWN

        try:
            return handler.status()
        except Exception as e:
            self.logger.error(f"Failed to check service status: {e}")
            return ServiceState.UNKNOWN

    def is_installed(self) -> bool:
        """
        Check if service is installed.

        Returns:
            True if service is installed, False otherwise
        """
        handler = self._handlers.get(self.platform)
        if not handler:
            return False

        try:
            return handler.is_installed()
        except Exception as e:
            self.logger.error(f"Failed to check installation status: {e}")
            return False
