"""Handler for macOS LaunchAgent."""

import subprocess
import sys
from pathlib import Path

from airunner_services.service_manager.service_handler_base import (
    ServiceHandlerBase,
)
from airunner_services.service_manager.service_state import ServiceState


class MacOSLaunchAgentHandler(ServiceHandlerBase):
    """Handler for macOS LaunchAgent."""

    SERVICE_NAME = "com.capsize-games.airunner"

    def __init__(self):
        super().__init__()
        self.plist_file = (
            Path.home()
            / "Library"
            / "LaunchAgents"
            / f"{self.SERVICE_NAME}.plist"
        )

    def install(self, config_path: Path, **kwargs) -> bool:
        """Install LaunchAgent plist."""
        python_exe = sys.executable
        daemon_script = Path(python_exe).parent / "airunner-daemon"

        if not daemon_script.exists():
            daemon_cmd = [python_exe, "-m", "airunner.services.daemon"]
        else:
            daemon_cmd = [str(daemon_script)]

        # Add config path
        daemon_cmd.extend(["--config", str(config_path)])

        # Create plist content
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{self.SERVICE_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        {''.join(f'<string>{arg}</string>' for arg in daemon_cmd)}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>{Path.home()}/Library/Logs/airunner.log</string>
    <key>StandardErrorPath</key>
    <string>{Path.home()}/Library/Logs/airunner.error.log</string>
</dict>
</plist>
"""

        try:
            # Create LaunchAgents directory if it doesn't exist
            self.plist_file.parent.mkdir(parents=True, exist_ok=True)

            # Write plist file
            self.plist_file.write_text(plist_content)
            self.logger.info(f"Created plist file: {self.plist_file}")

            # Load the agent
            if kwargs.get("load", True):
                subprocess.run(
                    ["launchctl", "load", str(self.plist_file)],
                    check=True,
                    capture_output=True,
                )
                self.logger.info(f"Loaded {self.SERVICE_NAME} LaunchAgent")

            return True

        except Exception as e:
            self.logger.error(f"Failed to install LaunchAgent: {e}")
            return False

    def uninstall(self) -> bool:
        """Uninstall LaunchAgent."""
        try:
            # Unload the agent
            subprocess.run(
                ["launchctl", "unload", str(self.plist_file)],
                capture_output=True,
            )

            # Remove plist file
            if self.plist_file.exists():
                self.plist_file.unlink()
                self.logger.info(f"Removed plist file: {self.plist_file}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to uninstall LaunchAgent: {e}")
            return False

    def start(self) -> bool:
        """Start LaunchAgent."""
        try:
            result = subprocess.run(
                ["launchctl", "start", self.SERVICE_NAME],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception as e:
            self.logger.error(f"Failed to start LaunchAgent: {e}")
            return False

    def stop(self) -> bool:
        """Stop LaunchAgent."""
        try:
            result = subprocess.run(
                ["launchctl", "stop", self.SERVICE_NAME],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception as e:
            self.logger.error(f"Failed to stop LaunchAgent: {e}")
            return False

    def status(self) -> ServiceState:
        """Get LaunchAgent status."""
        try:
            result = subprocess.run(
                ["launchctl", "list", self.SERVICE_NAME],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                # Check if PID is present in output
                if "PID" in result.stdout or '"PID" =' in result.stdout:
                    return ServiceState.RUNNING
                else:
                    return ServiceState.STOPPED
            else:
                return ServiceState.UNKNOWN

        except Exception as e:
            self.logger.error(f"Failed to get LaunchAgent status: {e}")
            return ServiceState.UNKNOWN

    def is_installed(self) -> bool:
        """Check if LaunchAgent is installed."""
        return self.plist_file.exists()
