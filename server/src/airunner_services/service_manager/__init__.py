"""Cross-platform service manager for AI Runner, one class per file."""

from airunner_services.service_manager.linux_systemd_handler import (
    LinuxSystemdHandler,
)
from airunner_services.service_manager.macos_launch_agent_handler import (
    MacOSLaunchAgentHandler,
)
from airunner_services.service_manager.service_handler_base import (
    ServiceHandlerBase,
)
from airunner_services.service_manager.service_manager import (
    ServiceManager,
    logger,
)
from airunner_services.service_manager.service_platform import (
    ServicePlatform,
)
from airunner_services.service_manager.service_state import ServiceState
from airunner_services.service_manager.windows_service_handler import (
    WindowsServiceHandler,
)

__all__ = [
    "LinuxSystemdHandler",
    "MacOSLaunchAgentHandler",
    "ServiceHandlerBase",
    "ServiceManager",
    "ServicePlatform",
    "ServiceState",
    "WindowsServiceHandler",
    "logger",
]
