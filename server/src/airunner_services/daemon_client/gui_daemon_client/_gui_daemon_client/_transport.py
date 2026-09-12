"""HTTP transport helpers for GuiDaemonClient."""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from airunner_services.daemon_connection_state import (
    DaemonConnectionState,
)


class GuiDaemonClientTransportMixin:
    """Perform HTTP requests against the daemon with state tracking."""

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
        auto_start: bool = True,
        timeout_seconds: Optional[float] = None,
    ) -> requests.Response:
        """Perform an HTTP request against the daemon."""
        if not self.ensure_connected(auto_start=auto_start):
            raise RuntimeError(self._last_error or "daemon unavailable")

        # Forward the active tenant so the (loopback) daemon scopes its DB
        # work to the caller's schema. The daemon's tenant middleware honors
        # ``x-tenant-key`` on loopback requests.
        headers = self._with_tenant_header(headers)

        try:
            response = self._session.request(
                method,
                f"{self.base_url}{path}",
                json=json_payload,
                files=files,
                headers=headers,
                stream=stream,
                timeout=timeout_seconds or self._request_timeout_seconds,
            )
            response.raise_for_status()
            self._set_state(DaemonConnectionState.CONNECTED, "connected")
            return response
        except requests.RequestException as exc:
            self._last_error = str(exc)
            self._set_state(
                DaemonConnectionState.DISCONNECTED, self._last_error
            )
            raise RuntimeError(self._last_error) from exc

    @staticmethod
    def _with_tenant_header(
        headers: Optional[Dict[str, str]],
    ) -> Optional[Dict[str, str]]:
        """Return headers augmented with the active tenant key, if any."""
        from airunner_services.data.tenant import get_tenant_key

        tenant_key = get_tenant_key()
        if not tenant_key:
            return headers
        merged = dict(headers or {})
        merged.setdefault("x-tenant-key", tenant_key)
        return merged

    def _runtime_action(
        self,
        runtime_name: str,
        action: str,
        *,
        provider: str,
        deployment_mode: str,
        request_id: Optional[str],
        metadata: Optional[Dict[str, Any]],
        auto_start: bool,
        timeout_seconds: Optional[float],
    ) -> Dict[str, Any]:
        """Call one daemon runtime control endpoint and return its payload."""
        response = self._request(
            "POST",
            f"/api/v1/daemon/runtimes/{runtime_name}/{action}",
            json_payload={
                "provider": provider,
                "deployment_mode": deployment_mode,
                "request_id": request_id,
                "metadata": metadata or {},
            },
            auto_start=auto_start,
            timeout_seconds=timeout_seconds,
        )
        return response.json()

    @staticmethod
    def _runtime_matches(summary: Dict[str, Any], loaded: bool) -> bool:
        """Return True when one runtime summary matches the target state."""
        summary_loaded = bool(summary.get("loaded"))
        summary_status = str(summary.get("status", "")).lower()
        if loaded:
            return summary_loaded and summary_status == "ready"
        return not summary_loaded
