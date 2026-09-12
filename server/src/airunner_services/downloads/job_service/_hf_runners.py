"""HuggingFace background job runners for :class:`DownloadJobService`.

Both runners live on a background thread, capture the download worker's
signal emissions into the shared job tracker, and honor cancellation
through a watcher thread and the worker's ``is_cancelled`` flag.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

from airunner_services.contract_enums import SignalCode as WorkerSignalCode
from airunner_services.downloads.huggingface import (
    HuggingFaceDownloadRequest,
)
from airunner_services.downloads.job_service._helpers import (
    _coerce_progress,
)
from airunner_services.downloads.persistent_job_tracker import JobStatus
from airunner_services.llm.utils.model_downloader import (
    DownloadCancelledError,
)


class DownloadJobHfRunnersMixin:
    """Run HuggingFace download jobs inside background threads."""

    def _run_huggingface_job(
        self,
        job_id: str,
        cancel_event: threading.Event,
        request: HuggingFaceDownloadRequest,
    ) -> None:
        """Run one HuggingFace download inside a background thread."""
        self._update_job(job_id, 0.0, JobStatus.RUNNING)
        worker = self._huggingface_worker_factory()
        completion: dict[str, Any] | None = None
        failure: str | None = None
        stop_watch = threading.Event()

        def handle_signal(
            code: object, data: dict[str, Any] | None = None
        ) -> None:
            nonlocal completion, failure
            payload = data or {}
            if code == WorkerSignalCode.UPDATE_DOWNLOAD_LOG:
                self._record_log_message(
                    job_id, str(payload.get("message") or "")
                )
                return
            if code == WorkerSignalCode.UPDATE_DOWNLOAD_PROGRESS:
                progress = float(payload.get("progress") or 0.0)
                self._update_job(job_id, progress, JobStatus.RUNNING)
                return
            if code == WorkerSignalCode.UPDATE_FILE_DOWNLOAD_PROGRESS:
                self._record_file_progress(
                    job_id,
                    str(payload.get("filename") or ""),
                    int(payload.get("downloaded") or 0),
                    int(payload.get("total") or 0),
                )
                return
            if code == WorkerSignalCode.HUGGINGFACE_DOWNLOAD_COMPLETE:
                completion = payload
                return
            if code == WorkerSignalCode.HUGGINGFACE_DOWNLOAD_FAILED:
                failure = str(payload.get("error") or "Download failed")

        def watch_cancel() -> None:
            while not stop_watch.is_set():
                if cancel_event.is_set():
                    worker.is_cancelled = True
                    return
                time.sleep(0.05)

        worker.emit_signal = handle_signal  # type: ignore[method-assign]
        cancel_watcher = threading.Thread(target=watch_cancel, daemon=True)
        cancel_watcher.start()
        try:
            worker.handle_message(request.as_payload())
            if cancel_event.is_set() or worker.is_cancelled:
                self._cancel_job(job_id)
                return
            if failure is not None:
                self._fail_job(job_id, failure)
                return
            if completion is None:
                self._fail_job(
                    job_id,
                    "Download ended without completion signal",
                )
                return
            model_path = str(
                completion.get("model_path") or request.output_dir or ""
            )
            self._complete_job(
                job_id,
                {
                    "provider": "huggingface",
                    "repo_id": str(
                        completion.get("repo_id") or request.repo_id
                    ),
                    "model_type": str(
                        completion.get("model_type") or request.model_type
                    ),
                    "paths": [model_path] if model_path else [],
                    "pipeline_action": completion.get("pipeline_action"),
                },
            )
        except Exception as exc:
            self._fail_job(job_id, str(exc))
        finally:
            stop_watch.set()
            cancel_watcher.join(timeout=0.1)
            self._forget_job(job_id)

    def _run_huggingface_file_job(
        self,
        job_id: str,
        cancel_event: threading.Event,
        repo_id: str,
        filename: str,
        output_dir: str,
    ) -> None:
        """Run one single-file HuggingFace download inside a background thread."""
        self._update_job(job_id, 0.0, JobStatus.RUNNING)
        self._record_log_message(job_id, f"Starting download: {filename}")
        last_progress = -1.0

        def progress(downloaded: int, total: int) -> None:
            nonlocal last_progress
            current_progress = _coerce_progress(downloaded, total)
            if (
                current_progress < 100.0
                and current_progress - last_progress < 1.0
            ):
                return
            last_progress = current_progress
            asyncio.run(
                self._tracker.update_progress(
                    job_id,
                    current_progress,
                    JobStatus.RUNNING,
                )
            )
            self._record_file_progress(
                job_id,
                filename,
                downloaded,
                total,
            )

        try:
            path = self._huggingface_downloader.download_file(
                repo_id,
                filename,
                output_dir,
                progress_callback=progress,
                cancel_callback=cancel_event.is_set,
            )
            self._complete_job(
                job_id,
                {
                    "provider": "huggingface",
                    "repo_id": repo_id,
                    "filename": filename,
                    "paths": [str(path)],
                },
            )
        except DownloadCancelledError:
            self._cancel_job(job_id)
        except Exception as exc:
            self._fail_job(job_id, str(exc))
        finally:
            self._forget_job(job_id)
