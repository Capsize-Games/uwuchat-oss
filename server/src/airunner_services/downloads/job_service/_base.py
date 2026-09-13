"""Job lifecycle state and shared tracker helpers.

Base mixin for :class:`DownloadJobService`.  Owns the mutable job
registry (threads and cancel events) created in :meth:`__init__`, the
public status/result/cancel surface, the synchronous wrappers, and the
small tracker-update helpers used by the background runners in the
sibling runner mixins.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable

from airunner_services.downloads.huggingface_download_worker import (
    HuggingFaceDownloadWorker as ServiceHuggingFaceDownloadWorker,
)
from airunner_services.downloads.persistent_job_tracker import (
    JobState,
    JobStatus,
    PersistentJobTracker,
)
from airunner_services.llm.utils.model_downloader import (
    HuggingFaceDownloader as SimpleHuggingFaceDownloader,
)


class DownloadJobBase:
    """Own the download job registry and shared tracker helpers."""

    def __init__(
        self,
        tracker: PersistentJobTracker | None = None,
        huggingface_downloader: SimpleHuggingFaceDownloader | None = None,
        huggingface_worker_factory: (
            Callable[[], ServiceHuggingFaceDownloadWorker] | None
        ) = None,
    ) -> None:
        self._tracker = tracker or PersistentJobTracker()
        self._huggingface_downloader = (
            huggingface_downloader or SimpleHuggingFaceDownloader()
        )
        self._huggingface_worker_factory = (
            huggingface_worker_factory or ServiceHuggingFaceDownloadWorker
        )
        self._cancel_events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    async def get_status(self, job_id: str) -> JobState | None:
        """Return the tracked state for one download job."""
        return await self._tracker.get_status(job_id)

    async def get_result(
        self,
        job_id: str,
        timeout: float = 300.0,
    ) -> Any:
        """Return the terminal result for one download job."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            job = await self._tracker.get_status(job_id)
            if job is None:
                raise ValueError(f"Job {job_id} not found")
            if job.status == JobStatus.COMPLETED:
                return job.result
            if job.status == JobStatus.FAILED:
                raise Exception(job.error or "Job failed")
            if job.status == JobStatus.CANCELLED:
                raise Exception("Job cancelled")
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"Job {job_id} timed out")
            await asyncio.sleep(0.05)

    async def cancel(self, job_id: str) -> bool:
        """Request cancellation for one running download job."""
        with self._lock:
            cancel_event = self._cancel_events.get(job_id)
        if cancel_event is not None:
            cancel_event.set()
        return await self._tracker.cancel_job(job_id)

    def start_huggingface_download_sync(
        self, *args: Any, **kwargs: Any
    ) -> str:
        """Synchronously create one HuggingFace download job."""
        return asyncio.run(self.start_huggingface_download(*args, **kwargs))

    def start_huggingface_file_download_sync(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Synchronously create one single-file HuggingFace download job."""
        return asyncio.run(
            self.start_huggingface_file_download(*args, **kwargs)
        )

    def start_civitai_file_download_sync(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Synchronously create one single-file CivitAI download job."""
        return asyncio.run(self.start_civitai_file_download(*args, **kwargs))

    def start_url_download_sync(self, *args: Any, **kwargs: Any) -> str:
        """Synchronously create one generic URL download job."""
        return asyncio.run(self.start_url_download(*args, **kwargs))

    def start_nltk_download_sync(self, *args: Any, **kwargs: Any) -> str:
        """Synchronously create one NLTK data download job."""
        return asyncio.run(self.start_nltk_download(*args, **kwargs))

    def get_status_sync(self, job_id: str) -> JobState | None:
        """Synchronously return the status for one tracked job."""
        return asyncio.run(self.get_status(job_id))

    def cancel_sync(self, job_id: str) -> bool:
        """Synchronously cancel one tracked job."""
        return asyncio.run(self.cancel(job_id))

    def _record_log_message(self, job_id: str, message: str) -> None:
        """Persist one user-facing log message into job metadata."""
        if not message:
            return
        self._update_job_metadata(
            job_id,
            {"last_log_message": message},
        )

    def _record_file_progress(
        self,
        job_id: str,
        filename: str,
        downloaded: int,
        total: int,
    ) -> None:
        """Persist one file-progress update into job metadata."""
        if not filename:
            return
        self._update_job_metadata(
            job_id,
            {
                "file_progress": {
                    "filename": filename,
                    "downloaded": max(0, int(downloaded)),
                    "total": max(0, int(total)),
                }
            },
        )

    def _update_job_metadata(
        self,
        job_id: str,
        metadata: dict[str, Any],
    ) -> None:
        """Push one metadata update into the shared tracker."""
        asyncio.run(self._tracker.update_metadata(job_id, metadata))

    def _update_job(
        self,
        job_id: str,
        progress: float,
        status: str,
    ) -> None:
        """Push one status update into the shared tracker."""
        asyncio.run(self._tracker.update_progress(job_id, progress, status))

    def _complete_job(self, job_id: str, result: dict[str, Any]) -> None:
        """Mark one job as complete in the shared tracker."""
        asyncio.run(self._tracker.complete_job(job_id, result))

    def _fail_job(self, job_id: str, error: str) -> None:
        """Mark one job as failed in the shared tracker."""
        asyncio.run(self._tracker.fail_job(job_id, error))

    def _cancel_job(self, job_id: str) -> None:
        """Mark one job as cancelled in the shared tracker."""
        asyncio.run(self._tracker.cancel_job(job_id))

    def _forget_job(self, job_id: str) -> None:
        """Drop one finished thread and cancel token from local state."""
        with self._lock:
            self._cancel_events.pop(job_id, None)
            self._threads.pop(job_id, None)
