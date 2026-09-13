"""Stale daemon detection and recycling for GuiDaemonClient."""

from __future__ import annotations

import os
import signal
import subprocess
from typing import Any, Dict, Optional

import requests

from airunner_services.daemon_connection_state import (
    DaemonConnectionState,
)
from airunner_services.dev_build_token import current_dev_build_token


class GuiDaemonClientStaleDaemonMixin:
    """Detect and recycle stale dev daemons before connecting."""

    def _expected_dev_build_token(self) -> Optional[str]:
        """Return the current expected dev build token for this client."""
        if not self._detect_stale_dev_daemon:
            return None
        now = self._time_fn()
        if now - self._dev_build_token_checked_at < 2.0:
            return self._cached_dev_build_token
        self._cached_dev_build_token = current_dev_build_token()
        self._dev_build_token_checked_at = now
        return self._cached_dev_build_token

    def _stale_dev_daemon_reason(
        self,
        health: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Return a mismatch reason when a dev daemon is stale."""
        expected = self._expected_dev_build_token()
        if health is None or not expected:
            return None
        observed = str(health.get("dev_build_token") or "").strip()
        if not observed:
            if not self._missing_dev_build_token_logged:
                self.logger.debug(
                    "Daemon health payload missing dev_build_token; "
                    "skipping stale-daemon recycle"
                )
                self._missing_dev_build_token_logged = True
            return None
        self._missing_dev_build_token_logged = False
        if observed != expected:
            return "stale dev daemon build token mismatch"
        return None

    def _recycle_stale_daemon(self, reason: str) -> bool:
        """Stop one stale local daemon so a fresh one can be launched."""
        self.logger.info("Recycling daemon: %s", reason)
        self._request_daemon_shutdown()
        if not self._wait_until_unavailable(5.0):
            self._terminate_port_owner()
        if self._wait_until_unavailable(5.0):
            self._set_state(DaemonConnectionState.RECONNECTING, reason)
            return True
        self._last_error = "Timed out stopping stale daemon"
        self._set_state(DaemonConnectionState.FAILED, self._last_error)
        return False

    def _request_daemon_shutdown(self) -> None:
        """Ask a reachable daemon on this port to shut itself down."""
        try:
            response = self._session.request(
                "POST",
                f"{self.base_url}/admin/shutdown",
                timeout=5,
            )
            response.raise_for_status()
        except requests.RequestException:
            self.logger.debug("Daemon shutdown request failed", exc_info=True)

    def _wait_until_unavailable(self, timeout_seconds: float) -> bool:
        """Return True once the daemon no longer answers /health."""
        deadline = self._time_fn() + timeout_seconds
        while self._time_fn() < deadline:
            if self._healthcheck_payload() is None:
                return True
            self._sleep(self._poll_interval_seconds)
        return False

    def _terminate_port_owner(self) -> None:
        """Send SIGTERM to any process listening on the configured port."""
        port = self.config.config.get("server", {}).get("port", 8188)
        for pid in self._pids_on_port(port):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                self.logger.debug("Failed to terminate pid=%s", pid)

    def _pids_on_port(self, port: int) -> list[int]:
        """Return process ids currently listening on one TCP port."""
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return []
        return [int(pid) for pid in result.stdout.split() if pid.isdigit()]
