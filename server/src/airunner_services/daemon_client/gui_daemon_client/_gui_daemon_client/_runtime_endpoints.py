"""Runtime and TTS endpoint wrappers for GuiDaemonClient."""

from __future__ import annotations

from typing import Any, Dict, Optional

from airunner_services.contract_enums import ModelService


class GuiDaemonClientRuntimeEndpointsMixin:
    """Daemon control and TTS endpoints."""

    def interrupt_llm(self) -> Dict[str, Any]:
        """Interrupt the active daemon-side LLM request."""
        response = self._request(
            "POST",
            "/admin/interrupt",
            json_payload={"kind": "process"},
            auto_start=False,
        )
        return response.json()

    def unload_local_llm(
        self,
        *,
        auto_start: bool = False,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Interrupt and queue unload for the daemon's local-worker LLM."""
        response = self._request(
            "POST",
            "/admin/llm/unload",
            auto_start=auto_start,
            timeout_seconds=timeout_seconds,
        )
        return response.json()

    def daemon_runtime_status(
        self,
        *,
        auto_start: bool = False,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Return combined daemon lifecycle and runtime status."""
        response = self._request(
            "GET",
            "/api/v1/daemon/status",
            auto_start=auto_start,
            timeout_seconds=timeout_seconds,
        )
        return response.json()

    def runtime_status(
        self,
        runtime_name: str,
        *,
        provider: str = ModelService.LOCAL.value,
        deployment_mode: str = "default",
        auto_start: bool = False,
    ) -> Dict[str, Any]:
        """Return the daemon summary for one runtime route."""
        from urllib.parse import urlencode

        query = urlencode(
            {
                "provider": provider,
                "deployment_mode": deployment_mode,
            }
        )
        response = self._request(
            "GET",
            f"/api/v1/daemon/runtimes/{runtime_name}?{query}",
            auto_start=auto_start,
        )
        return response.json()

    def wait_runtime_ready(
        self,
        runtime_name: str,
        *,
        loaded: bool,
        provider: str = ModelService.LOCAL.value,
        deployment_mode: str = "default",
        auto_start: bool = False,
        timeout_seconds: float = 30.0,
    ) -> bool:
        """Poll one runtime summary until it reaches the requested state."""
        deadline = self._time_fn() + timeout_seconds
        while self._time_fn() < deadline:
            try:
                summary = self.runtime_status(
                    runtime_name,
                    provider=provider,
                    deployment_mode=deployment_mode,
                    auto_start=auto_start,
                )
            except RuntimeError:
                self._sleep(self._poll_interval_seconds)
                continue
            if self._runtime_matches(summary, loaded):
                return True
            self._sleep(self._poll_interval_seconds)
        return False

    def cancel_runtime(
        self,
        runtime_name: str,
        *,
        provider: str = ModelService.LOCAL.value,
        deployment_mode: str = "default",
        request_id: Optional[str] = None,
        auto_start: bool = False,
    ) -> Dict[str, Any]:
        """Cancel one runtime request through the daemon control API."""
        return self._runtime_action(
            runtime_name,
            "cancel",
            provider=provider,
            deployment_mode=deployment_mode,
            request_id=request_id,
            auto_start=auto_start,
        )

    def load_runtime(
        self,
        runtime_name: str,
        *,
        provider: str = ModelService.LOCAL.value,
        deployment_mode: str = "default",
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auto_start: bool = True,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Load one runtime through the daemon control API."""
        return self._runtime_action(
            runtime_name,
            "load",
            provider=provider,
            deployment_mode=deployment_mode,
            request_id=request_id,
            metadata=metadata,
            auto_start=auto_start,
            timeout_seconds=timeout_seconds,
        )

    def unload_runtime(
        self,
        runtime_name: str,
        *,
        provider: str = ModelService.LOCAL.value,
        deployment_mode: str = "default",
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auto_start: bool = True,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Unload one runtime through the daemon control API."""
        return self._runtime_action(
            runtime_name,
            "unload",
            provider=provider,
            deployment_mode=deployment_mode,
            request_id=request_id,
            metadata=metadata,
            auto_start=auto_start,
            timeout_seconds=timeout_seconds,
        )

    def synthesize_tts(
        self,
        text: str,
        *,
        voice: Optional[str] = None,
        speed: float = 1.0,
        model: Optional[str] = None,
        model_type: Optional[str] = None,
        request_id: Optional[str] = None,
        auto_start: bool = True,
    ) -> bytes:
        """Synthesize one TTS utterance through the daemon TTS route."""
        response = self._request(
            "POST",
            "/api/v1/tts/synthesize",
            json_payload={
                "text": text,
                "voice": voice,
                "speed": speed,
                "model": model,
                "model_type": model_type,
                "request_id": request_id,
            },
            auto_start=auto_start,
            timeout_seconds=120.0,
        )
        return response.content

    def transcribe_audio(
        self,
        audio_bytes: bytes,
        *,
        mime_type: str = "application/octet-stream",
        auto_start: bool = True,
    ) -> Dict[str, Any]:
        """Submit one STT transcription request through the daemon API."""
        response = self._request(
            "POST",
            "/api/v1/stt/transcribe",
            files={
                "audio": (
                    "audio.bin",
                    audio_bytes,
                    mime_type,
                )
            },
            auto_start=auto_start,
            timeout_seconds=120.0,
        )
        return response.json()
