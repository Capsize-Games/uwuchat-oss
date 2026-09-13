"""Download endpoint wrappers for GuiDaemonClient."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional


class GuiDaemonClientDownloadEndpointsMixin:
    """Daemon download job endpoints."""

    def start_huggingface_download(
        self,
        repo_id: str,
        *,
        model_type: str = "llm",
        output_dir: Optional[str] = None,
        missing_files: Optional[list[str]] = None,
        gguf_filename: Optional[str] = None,
        prefer_pre_quantized: bool = True,
        auto_start: bool = True,
    ) -> Dict[str, Any]:
        """Queue one daemon-backed HuggingFace download job."""
        response = self._request(
            "POST",
            "/api/v1/downloads/huggingface",
            json_payload={
                "repo_id": repo_id,
                "model_type": model_type,
                "output_dir": output_dir,
                "missing_files": missing_files,
                "gguf_filename": gguf_filename,
                "prefer_pre_quantized": prefer_pre_quantized,
            },
            auto_start=auto_start,
            timeout_seconds=30.0,
        )
        return response.json()

    def start_url_download(
        self,
        url: str,
        *,
        output_dir: str,
        filename: Optional[str] = None,
        extract_zip: bool = False,
        auto_start: bool = True,
    ) -> Dict[str, Any]:
        """Queue one daemon-backed generic URL download job."""
        response = self._request(
            "POST",
            "/api/v1/downloads/url",
            json_payload={
                "url": url,
                "output_dir": output_dir,
                "filename": filename,
                "extract_zip": extract_zip,
            },
            auto_start=auto_start,
            timeout_seconds=30.0,
        )
        return response.json()

    def download_job_status(
        self,
        job_id: str,
        *,
        auto_start: bool = False,
    ) -> Dict[str, Any]:
        """Return the current daemon-backed download job state."""
        response = self._request(
            "GET",
            f"/api/v1/downloads/status/{job_id}",
            auto_start=auto_start,
        )
        return response.json()

    def wait_download_job(
        self,
        job_id: str,
        *,
        auto_start: bool = False,
        timeout_seconds: float = 1800.0,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Poll one download job until it reaches a terminal state."""
        deadline = self._time_fn() + timeout_seconds
        last_status: Optional[str] = None
        last_progress: Optional[float] = None
        while self._time_fn() < deadline:
            status = self.download_job_status(job_id, auto_start=auto_start)
            state = str(status.get("status", "")).lower()
            progress = float(status.get("progress") or 0.0)
            if progress_callback is not None and (
                state != last_status or progress != last_progress
            ):
                progress_callback(status)
            if state == "completed":
                return status
            if state == "failed":
                raise RuntimeError(
                    str(status.get("error") or "Download job failed")
                )
            if state == "cancelled":
                raise RuntimeError("Download job cancelled")
            last_status = state
            last_progress = progress
            self._sleep(self._poll_interval_seconds)
        try:
            self.cancel_download_job(job_id, auto_start=False)
        except RuntimeError:
            pass
        raise RuntimeError("Timed out waiting for download job")

    def cancel_download_job(
        self,
        job_id: str,
        *,
        auto_start: bool = False,
    ) -> Dict[str, Any]:
        """Cancel one daemon-backed download job."""
        response = self._request(
            "DELETE",
            f"/api/v1/downloads/cancel/{job_id}",
            auto_start=auto_start,
        )
        return response.json()
