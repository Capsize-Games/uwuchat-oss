"""Handler for Windows services using NSSM."""

import subprocess
import sys
from pathlib import Path

from airunner_services.service_manager.service_handler_base import (
    ServiceHandlerBase,
)
from airunner_services.service_manager.service_state import ServiceState


class WindowsServiceHandler(ServiceHandlerBase):
    """Handler for Windows services using NSSM."""

    SERVICE_NAME = "AIRunner"

    def install(self, config_path: Path, **kwargs) -> bool:
        """Install Windows service using NSSM."""
        # Check if NSSM is installed
        try:
            subprocess.run(
                ["nssm", "version"], capture_output=True, check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.logger.error(
                "NSSM not found. Please install NSSM from https://nssm.cc/"
            )
            return False

        python_exe = sys.executable
        daemon_script = Path(python_exe).parent / "airunner-daemon.exe"

        if not daemon_script.exists():
            # Use Python module execution
            app_path = python_exe
            app_args = f"-m airunner.services.daemon --config {config_path}"
        else:
            app_path = str(daemon_script)
            app_args = f"--config {config_path}"

        try:
            # Install service
            subprocess.run(
                ["nssm", "install", self.SERVICE_NAME, app_path]
                + app_args.split(),
                check=True,
                capture_output=True,
            )

            # Set service description
            subprocess.run(
                [
                    "nssm",
                    "set",
                    self.SERVICE_NAME,
                    "Description",
                    "AI Runner Background Service",
                ],
                capture_output=True,
            )

            # Set startup type to automatic
            subprocess.run(
                [
                    "nssm",
                    "set",
                    self.SERVICE_NAME,
                    "Start",
                    "SERVICE_AUTO_START",
                ],
                capture_output=True,
            )

            self.logger.info(f"Installed {self.SERVICE_NAME} Windows service")
            return True

        except Exception as e:
            self.logger.error(f"Failed to install Windows service: {e}")
            return False

    def uninstall(self) -> bool:
        """Uninstall Windows service."""
        try:
            # Stop service first
            subprocess.run(
                ["nssm", "stop", self.SERVICE_NAME], capture_output=True
            )

            # Remove service
            subprocess.run(
                ["nssm", "remove", self.SERVICE_NAME, "confirm"],
                check=True,
                capture_output=True,
            )

            self.logger.info(
                f"Uninstalled {self.SERVICE_NAME} Windows service"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to uninstall Windows service: {e}")
            return False

    def start(self) -> bool:
        """Start Windows service."""
        try:
            result = subprocess.run(
                ["nssm", "start", self.SERVICE_NAME],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception as e:
            self.logger.error(f"Failed to start service: {e}")
            return False

    def stop(self) -> bool:
        """Stop Windows service."""
        try:
            result = subprocess.run(
                ["nssm", "stop", self.SERVICE_NAME],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception as e:
            self.logger.error(f"Failed to stop service: {e}")
            return False

    def status(self) -> ServiceState:
        """Get Windows service status."""
        try:
            result = subprocess.run(
                ["nssm", "status", self.SERVICE_NAME],
                capture_output=True,
                text=True,
            )

            status_str = result.stdout.strip().upper()
            if "RUNNING" in status_str or "SERVICE_RUNNING" in status_str:
                return ServiceState.RUNNING
            elif "STOPPED" in status_str or "SERVICE_STOPPED" in status_str:
                return ServiceState.STOPPED
            else:
                return ServiceState.UNKNOWN

        except Exception as e:
            self.logger.error(f"Failed to get service status: {e}")
            return ServiceState.UNKNOWN

    def is_installed(self) -> bool:
        """Check if Windows service is installed."""
        try:
            result = subprocess.run(
                ["nssm", "status", self.SERVICE_NAME],
                capture_output=True,
                text=True,
            )
            # If status command succeeds, service is installed
            return result.returncode == 0
        except Exception:
            return False
