"""Art endpoint wrappers for GuiDaemonClient."""

from __future__ import annotations

import base64
from typing import Any, Callable, Dict, Optional

_ART_JOB_POLL_INTERVAL_SECONDS = 0.10


class GuiDaemonClientArtEndpointsMixin:
    """Daemon art generation and component endpoints."""

    def start_art_generation(
        self,
        *,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 20,
        cfg_scale: float = 7.5,
        seed: Optional[int] = None,
        num_images: int = 1,
        model: Optional[str] = None,
        version: Optional[str] = None,
        scheduler: Optional[str] = None,
        pipeline: Optional[str] = None,
        strength: Optional[float] = None,
        image_b64: Optional[str] = None,
        skip_auto_export: bool = False,
        auto_start: bool = True,
    ) -> Dict[str, Any]:
        """Submit one art generation request through the daemon art route."""
        self.logger.info(
            "GuiDaemonClient.start_art_generation model=%s version=%s scheduler=%s steps=%s size=%sx%s",
            model,
            version,
            scheduler,
            steps,
            width,
            height,
        )
        response = self._request(
            "POST",
            "/api/v1/art/generate",
            json_payload={
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "steps": steps,
                "cfg_scale": cfg_scale,
                "seed": seed,
                "num_images": num_images,
                "model": model,
                "version": version,
                "scheduler": scheduler,
                "pipeline": pipeline,
                "strength": strength,
                "image_b64": image_b64,
                "skip_auto_export": skip_auto_export,
            },
            auto_start=auto_start,
            timeout_seconds=30.0,
        )
        return response.json()

    def art_job_status(
        self,
        job_id: str,
        *,
        auto_start: bool = False,
    ) -> Dict[str, Any]:
        """Return the current daemon art-job status payload."""
        response = self._request(
            "GET",
            f"/api/v1/art/status/{job_id}",
            auto_start=auto_start,
        )
        return response.json()

    def art_job_result(
        self,
        job_id: str,
        *,
        auto_start: bool = False,
    ) -> bytes:
        """Return the PNG payload for one completed daemon art job."""
        response = self._request(
            "GET",
            f"/api/v1/art/result/{job_id}",
            auto_start=auto_start,
            timeout_seconds=120.0,
        )
        return response.content

    def wait_art_job(
        self,
        job_id: str,
        *,
        auto_start: bool = False,
        timeout_seconds: float = 1800.0,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> bytes:
        """Poll one art job until it completes and return the PNG bytes."""
        deadline = self._time_fn() + timeout_seconds
        poll_interval = min(
            self._poll_interval_seconds,
            _ART_JOB_POLL_INTERVAL_SECONDS,
        )
        last_status: Optional[str] = None
        last_progress: Optional[float] = None
        while self._time_fn() < deadline:
            status = self.art_job_status(job_id, auto_start=auto_start)
            state = str(status.get("status", "")).lower()
            progress = float(status.get("progress") or 0.0)
            if progress_callback is not None and (
                state != last_status or progress != last_progress
            ):
                progress_callback(status)
            if state != last_status or progress != last_progress:
                self.logger.debug(
                    "GuiDaemonClient.wait_art_job job_id=%s status=%s progress=%.1f",
                    job_id,
                    state,
                    progress,
                )
                last_status = state
                last_progress = progress
            if state == "completed":
                return self.art_job_result(job_id, auto_start=auto_start)
            if state == "failed":
                raise RuntimeError(
                    str(status.get("error") or "Art generation failed")
                )
            if state == "cancelled":
                raise RuntimeError("Art generation cancelled")
            self._sleep(poll_interval)
        try:
            self.cancel_art_job(job_id, auto_start=False)
        except RuntimeError:
            pass
        raise RuntimeError("Timed out waiting for art generation")

    def cancel_art_job(
        self,
        job_id: str,
        *,
        auto_start: bool = False,
    ) -> Dict[str, Any]:
        """Cancel one daemon-backed art job."""
        response = self._request(
            "DELETE",
            f"/api/v1/art/cancel/{job_id}",
            auto_start=auto_start,
        )
        return response.json()

    def remove_background(
        self,
        image_binary: bytes,
        *,
        auto_start: bool = True,
    ) -> bytes:
        """Run background removal through the daemon art route."""
        response = self._request(
            "POST",
            "/api/v1/art/remove-background",
            json_payload={
                "image_b64": base64.b64encode(image_binary).decode("ascii")
            },
            auto_start=auto_start,
            timeout_seconds=120.0,
        )
        return response.content

    def load_art_component(
        self,
        component: str,
        *,
        auto_start: bool = True,
    ) -> Dict[str, Any]:
        """Load one explicit art component through the daemon route."""
        response = self._request(
            "POST",
            f"/api/v1/art/components/{component}/load",
            auto_start=auto_start,
            timeout_seconds=120.0,
        )
        return response.json()

    def unload_art_component(
        self,
        component: str,
        *,
        auto_start: bool = False,
    ) -> Dict[str, Any]:
        """Unload one explicit art component through the daemon route."""
        response = self._request(
            "DELETE",
            f"/api/v1/art/components/{component}/unload",
            auto_start=auto_start,
            timeout_seconds=120.0,
        )
        return response.json()
