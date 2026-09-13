"""NLTK corpus download runner for :class:`DownloadJobService`.

NLTK data downloads run on a background thread that temporarily raises
the interpreter recursion limit to accommodate the NLTK download
stack, then restores it in ``finally``.
"""

from __future__ import annotations

import sys
import threading

try:
    import nltk
except ImportError:
    nltk = None

from airunner_services.downloads.persistent_job_tracker import JobStatus


class DownloadJobNltkRunnerMixin:
    """Run one NLTK data download job inside a background thread."""

    def _run_nltk_download_job(
        self,
        job_id: str,
        cancel_event: threading.Event,
        data_names: list[str],
    ) -> None:
        """Run one NLTK data download job inside a background thread."""
        self._update_job(job_id, 0.0, JobStatus.RUNNING)
        if nltk is None:
            self._fail_job(job_id, "NLTK is not installed")
            self._forget_job(job_id)
            return

        original_limit = sys.getrecursionlimit()
        total = max(1, len(data_names))
        downloaded_names: list[str] = []

        try:
            sys.setrecursionlimit(1500)
            for index, data_name in enumerate(data_names, start=1):
                if cancel_event.is_set():
                    self._cancel_job(job_id)
                    return

                completed = bool(nltk.download(data_name, quiet=True))
                if not completed:
                    raise RuntimeError(f"Failed to download NLTK {data_name}")

                downloaded_names.append(data_name)
                progress = min(99.0, (float(index) / float(total)) * 100.0)
                self._update_job(job_id, progress, JobStatus.RUNNING)

            if cancel_event.is_set():
                self._cancel_job(job_id)
                return

            self._complete_job(
                job_id,
                {
                    "provider": "nltk",
                    "data_names": downloaded_names,
                },
            )
        except Exception as exc:
            self._fail_job(job_id, str(exc))
        finally:
            sys.setrecursionlimit(original_limit)
            self._forget_job(job_id)
