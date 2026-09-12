"""Handler for Linux systemd user services."""

import subprocess
import sys
from pathlib import Path

from airunner_services.config.runtime_layout import (
    build_runtime_directory_layout,
)
from airunner_services.runtimes.bundle_layout import (
    build_linux_bundle_layout,
)
from airunner_services.service_manager.service_handler_base import (
    ServiceHandlerBase,
)
from airunner_services.service_manager.service_state import ServiceState


class LinuxSystemdHandler(ServiceHandlerBase):
    """Handler for Linux systemd user services."""

    SERVICE_NAME = "airunner"

    def __init__(self):
        super().__init__()
        self.service_file = (
            Path.home()
            / ".config"
            / "systemd"
            / "user"
            / f"{self.SERVICE_NAME}.service"
        )

    def install(self, config_path: Path, **kwargs) -> bool:
        """Install systemd user service."""
        # Get Python executable and airunner-daemon path
        bundle_layout = build_linux_bundle_layout(
            python_executable=sys.executable
        )
        daemon_script = bundle_layout.daemon_executable()

        if daemon_script is None:
            # Fallback to module execution
            daemon_cmd = (
                f"{bundle_layout.python_executable} "
                "-m airunner.services.daemon"
            )
        else:
            daemon_cmd = str(daemon_script)

        layout = build_runtime_directory_layout()
        layout.ensure_exists()
        service_content = self._generate_service_content(
            daemon_cmd,
            config_path,
            bundle_layout,
        )

        try:
            # Create systemd user directory if it doesn't exist
            self.service_file.parent.mkdir(parents=True, exist_ok=True)

            # Write service file
            self.service_file.write_text(service_content)
            self.logger.info(f"Created service file: {self.service_file}")

            # Reload systemd daemon
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                check=True,
                capture_output=True,
            )

            # Enable service (auto-start on login)
            if kwargs.get("enable", True):
                subprocess.run(
                    ["systemctl", "--user", "enable", self.SERVICE_NAME],
                    check=True,
                    capture_output=True,
                )
                self.logger.info(f"Enabled {self.SERVICE_NAME} service")

            return True

        except Exception as e:
            self.logger.error(f"Failed to install systemd service: {e}")
            return False

    def _generate_service_content(
        self,
        daemon_cmd: str,
        config_path: Path,
        bundle_layout=None,
    ) -> str:
        """Return the full systemd unit content for the daemon service."""
        bundle_layout = bundle_layout or build_linux_bundle_layout()
        environment = "\n".join(
            self._environment_lines(config_path, bundle_layout)
        )
        prestart = "\n".join(self._prestart_lines())
        security = "\n".join(self._security_lines())
        return f"""[Unit]
Description=AI Runner Background Service
After=network.target

[Service]
Type=simple
WorkingDirectory={bundle_layout.bundle_root}
{environment}
{prestart}
ExecStart={daemon_cmd} --config {config_path}
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
{security}

[Install]
WantedBy=default.target
"""

    def _environment_lines(
        self, config_path: Path, bundle_layout
    ) -> list[str]:
        """Return environment lines for the systemd unit."""
        layout = build_runtime_directory_layout()
        environment = layout.as_environment(config_path)
        environment.update(
            {
                "AIRUNNER_BUNDLE_ROOT": str(bundle_layout.bundle_root),
                "AIRUNNER_DAEMON": "1",
                "AIRUNNER_HTTP_HOST": "127.0.0.1",
                "AIRUNNER_RUNTIME_BIND_HOST": "127.0.0.1",
                "AIRUNNER_LLM_ON": "1",
                "AIRUNNER_PYTHON": str(bundle_layout.python_executable),
                "AIRUNNER_LOG_LEVEL": "INFO",
                "QT_QPA_PLATFORM": "offscreen",
                "QT_LOGGING_RULES": "*.debug=false;qt.qpa.*=false",
                "DEV_ENV": "0",
                "PATH": bundle_layout.path_environment(),
            }
        )
        return [
            f'Environment="{key}={value}"'
            for key, value in environment.items()
        ]

    def _prestart_lines(self) -> list[str]:
        """Return directory preparation commands for the service."""
        layout = build_runtime_directory_layout()
        managed = " ".join(str(path) for path in layout._managed_paths())
        return [
            f"ExecStartPre=/bin/mkdir -p {managed}",
            f"ExecStartPre=/bin/chmod 700 {managed}",
        ]

    def _security_lines(self) -> list[str]:
        """Return conservative least-privilege systemd directives."""
        layout = build_runtime_directory_layout()
        return [
            "LimitNOFILE=65536",
            "UMask=0077",
            "NoNewPrivileges=yes",
            "PrivateTmp=yes",
            "ProtectSystem=full",
            "ProtectHome=read-only",
            f"ReadWritePaths={layout.base_path}",
            "RestrictSUIDSGID=yes",
            "LockPersonality=yes",
            "RestrictRealtime=yes",
        ]

    def uninstall(self) -> bool:
        """Uninstall systemd user service."""
        try:
            # Disable and stop service
            subprocess.run(
                ["systemctl", "--user", "disable", self.SERVICE_NAME],
                capture_output=True,
            )
            subprocess.run(
                ["systemctl", "--user", "stop", self.SERVICE_NAME],
                capture_output=True,
            )

            # Remove service file
            if self.service_file.exists():
                self.service_file.unlink()
                self.logger.info(f"Removed service file: {self.service_file}")

            # Reload systemd
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"], capture_output=True
            )

            return True

        except Exception as e:
            self.logger.error(f"Failed to uninstall systemd service: {e}")
            return False

    def start(self) -> bool:
        """Start systemd service."""
        try:
            result = subprocess.run(
                ["systemctl", "--user", "start", self.SERVICE_NAME],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception as e:
            self.logger.error(f"Failed to start service: {e}")
            return False

    def stop(self) -> bool:
        """Stop systemd service."""
        try:
            result = subprocess.run(
                ["systemctl", "--user", "stop", self.SERVICE_NAME],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception as e:
            self.logger.error(f"Failed to stop service: {e}")
            return False

    def status(self) -> ServiceState:
        """Get systemd service status."""
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", self.SERVICE_NAME],
                capture_output=True,
                text=True,
            )

            status_str = result.stdout.strip()
            if status_str == "active":
                return ServiceState.RUNNING
            elif status_str == "inactive":
                return ServiceState.STOPPED
            elif status_str == "failed":
                return ServiceState.FAILED
            else:
                return ServiceState.UNKNOWN

        except Exception as e:
            self.logger.error(f"Failed to get service status: {e}")
            return ServiceState.UNKNOWN

    def is_installed(self) -> bool:
        """Check if systemd service is installed."""
        return self.service_file.exists()
