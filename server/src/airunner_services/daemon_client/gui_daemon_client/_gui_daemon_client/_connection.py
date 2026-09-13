"""Connection lifecycle and state for GuiDaemonClient."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import requests

from airunner_services.daemon_client.launcher import DaemonLauncher
from airunner_services.daemon_connection_state import (
    DaemonConnectionState,
)
from airunner_services.runtimes.daemon_config import DaemonConfig
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

StateCallback = Callable[[DaemonConnectionState, str], None]


class GuiDaemonClientConnectionMixin:
    """Manage the daemon connection lifecycle and tracked state."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        *,
        launcher: Optional[DaemonLauncher] = None,
        session: Optional[requests.Session] = None,
        auto_start: bool = True,
        startup_timeout_seconds: float | None = None,
        poll_interval_seconds: float = 0.25,
        request_timeout_seconds: float = 30.0,
        detect_stale_dev_daemon: bool = False,
        state_callback: Optional[StateCallback] = None,
        time_fn: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = DaemonConfig(config_path)
        self._launcher = launcher or DaemonLauncher(self.config.config_path)
        self._session = session or requests.Session()
        self._auto_start = auto_start
        self._startup_timeout_seconds = startup_timeout_seconds or float(
            os.environ.get("AIRUNNER_DAEMON_STARTUP_TIMEOUT", "120")
        )
        self._poll_interval_seconds = poll_interval_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._detect_stale_dev_daemon = detect_stale_dev_daemon
        self._state_callback = state_callback
        self._time_fn = time_fn
        self._sleep = sleep
        self._state = DaemonConnectionState.NOT_STARTED
        self._last_error = ""
        self._dev_build_token_checked_at = 0.0
        self._cached_dev_build_token: Optional[str] = None
        self._missing_dev_build_token_logged = False
        self.logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

    @property
    def state(self) -> DaemonConnectionState:
        """Return the current daemon connection state."""
        return self._state

    @property
    def last_error(self) -> str:
        """Return the most recent daemon connection or request error."""
        return self._last_error

    @property
    def base_url(self) -> str:
        """Return the configured daemon base URL."""
        server = self.config.config.get("server", {})
        host = server.get("host", "127.0.0.1")
        port = server.get("port", 8188)
        return f"http://{host}:{port}"

    def ensure_connected(self, *, auto_start: Optional[bool] = None) -> bool:
        """Return True when the daemon is reachable, starting it when allowed."""
        health = self._healthcheck_payload()
        stale_reason = self._stale_dev_daemon_reason(health)
        if health is not None and stale_reason is None:
            self._set_state(DaemonConnectionState.CONNECTED, "connected")
            return True

        if stale_reason is not None:
            if not self._resolved_auto_start(auto_start):
                self._set_state(
                    DaemonConnectionState.DISCONNECTED,
                    stale_reason,
                )
                return False
            if not self._recycle_stale_daemon(stale_reason):
                return False

        if not self._resolved_auto_start(auto_start):
            self._set_state(
                DaemonConnectionState.DISCONNECTED,
                self._last_error or "daemon unavailable",
            )
            return False

        self._prepare_connection_attempt()
        try:
            self._launcher.start()
        except OSError as exc:
            self._last_error = str(exc)
            self._set_state(DaemonConnectionState.FAILED, self._last_error)
            return False
        return self._wait_until_ready()

    def reconnect(self) -> bool:
        """Force a reconnect attempt to the daemon."""
        self._set_state(DaemonConnectionState.RECONNECTING, "reconnecting")
        return self.ensure_connected(auto_start=True)

    def disconnect(self, *, stop_process: bool = False) -> None:
        """Mark the daemon disconnected and optionally stop the process."""
        if stop_process:
            self._launcher.stop()
        self._set_state(DaemonConnectionState.DISCONNECTED, "disconnected")

    def health_check(self) -> Dict[str, Any]:
        """Return the daemon health payload."""
        response = self._request("GET", "/health", auto_start=False)
        return response.json()

    def is_available(self, *, timeout_seconds: float = 0.2) -> bool:
        """Return True when the daemon is already reachable."""
        health = self._healthcheck_payload(timeout_seconds=timeout_seconds)
        stale_reason = self._stale_dev_daemon_reason(health)
        if health is not None and stale_reason is None:
            self._set_state(DaemonConnectionState.CONNECTED, "connected")
            return True

        if stale_reason is not None:
            self._last_error = stale_reason
        self._set_state(
            DaemonConnectionState.DISCONNECTED,
            self._last_error or "daemon unavailable",
        )
        return False

    def _resolved_auto_start(self, auto_start: Optional[bool]) -> bool:
        """Return the effective auto-start behavior for this call."""
        if auto_start is None:
            return self._auto_start
        return auto_start

    def _prepare_connection_attempt(self) -> None:
        """Set the state for a new connection attempt."""
        if self._state is DaemonConnectionState.NOT_STARTED:
            self._set_state(
                DaemonConnectionState.CONNECTING, "starting daemon"
            )
            return
        self._set_state(DaemonConnectionState.RECONNECTING, "starting daemon")

    def _wait_until_ready(self) -> bool:
        """Wait for the daemon health endpoint to become ready."""
        deadline = self._time_fn() + self._startup_timeout_seconds
        while self._time_fn() < deadline:
            exit_code = self._launcher.last_exit_code()
            if exit_code is not None:
                self._last_error = (
                    "Daemon process exited early with code " f"{exit_code}"
                )
                self._set_state(DaemonConnectionState.FAILED, self._last_error)
                return False
            health = self._healthcheck_payload()
            if (
                health is not None
                and self._stale_dev_daemon_reason(health) is None
            ):
                self._set_state(DaemonConnectionState.CONNECTED, "connected")
                return True
            self._sleep(self._poll_interval_seconds)

        self._last_error = "Timed out waiting for daemon to become ready"
        self._set_state(DaemonConnectionState.FAILED, self._last_error)
        return False

    def _healthcheck_payload(
        self, *, timeout_seconds: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        """Return the daemon /health payload when it is reachable."""
        try:
            response = self._session.request(
                "GET",
                f"{self.base_url}/health",
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            self._last_error = str(exc)
            return None

    def _set_state(self, state: DaemonConnectionState, details: str) -> None:
        """Update the tracked daemon connection state."""
        self._state = state
        if state in {
            DaemonConnectionState.DISCONNECTED,
            DaemonConnectionState.FAILED,
        }:
            self._last_error = details
        if self._state_callback is not None:
            self._state_callback(state, details)
