"""CivitAI and generic-URL background job runners.

All three runners download one or more files through the shared
``download_civitai_file`` helper, report throttled progress into the
job tracker, and honor cancellation through the passed-in event.
"""

from __future__ import annotations

import threading
import zipfile
from pathlib import Path

from airunner_services.downloads.civitai import (
    fetch_model_info_for_url,
    sanitize_filename,
    select_version,
)
from airunner_services.downloads.civitai_download import (
    get_files_to_download,
)
from airunner_services.downloads.job_service._helpers import (
    _civitai_progress_reporter,
    _coerce_progress,
)
from airunner_services.downloads.persistent_job_tracker import JobStatus
from airunner_services.downloads.service import download_civitai_file
from airunner_services.utils.zip_utils import safe_extract_zip


class DownloadJobCivitaiRunnersMixin:
    """Run CivitAI and generic-URL download jobs in background threads."""

    def _run_civitai_model_job(
        self,
        job_id: str,
        cancel_event: threading.Event,
        url: str,
        output_dir: str,
        api_key: str,
    ) -> None:
        """Run one CivitAI model download inside a background thread."""
        self._update_job(job_id, 0.0, JobStatus.RUNNING)
        try:
            model_info = fetch_model_info_for_url(url, api_key)
            version = model_info.get("selectedVersion") or select_version(
                model_info
            )
            if version is None:
                raise ValueError("No CivitAI model version available")
            model_name = sanitize_filename(
                str(model_info.get("name") or "civitai_model")
            )
            model_path = Path(output_dir) / model_name
            files_to_download = get_files_to_download(version, model_path)
            total_size = sum(
                max(0, int(file_info.get("size") or 0))
                for file_info in files_to_download
            )
            downloaded_size = 0
            downloaded_paths = []
            for file_info in files_to_download:
                file_total = max(0, int(file_info.get("size") or 0))
                progress = _civitai_progress_reporter(
                    job_id,
                    self._tracker,
                    downloaded_size,
                    total_size,
                )
                completed = download_civitai_file(
                    file_info["url"],
                    model_path / file_info["filename"],
                    file_total,
                    api_key=api_key,
                    progress_callback=progress,
                    cancel_callback=cancel_event.is_set,
                )
                if not completed or cancel_event.is_set():
                    self._cancel_job(job_id)
                    return
                downloaded_size += file_total
                downloaded_paths.append(
                    str(model_path / file_info["filename"])
                )
            if not files_to_download:
                downloaded_paths.append(str(model_path))
            self._complete_job(
                job_id,
                {
                    "provider": "civitai",
                    "url": url,
                    "model_name": model_name,
                    "paths": downloaded_paths,
                },
            )
        except Exception as exc:
            self._fail_job(job_id, str(exc))
        finally:
            self._forget_job(job_id)

    def _run_civitai_file_job(
        self,
        job_id: str,
        cancel_event: threading.Event,
        url: str,
        output_path: str,
        file_size: int,
        api_key: str,
    ) -> None:
        """Run one CivitAI file download inside a background thread."""
        self._update_job(job_id, 0.0, JobStatus.RUNNING)
        progress = _civitai_progress_reporter(
            job_id,
            self._tracker,
            0,
            file_size,
        )
        try:
            completed = download_civitai_file(
                url,
                output_path,
                file_size,
                api_key=api_key,
                progress_callback=progress,
                cancel_callback=cancel_event.is_set,
            )
            if not completed or cancel_event.is_set():
                self._cancel_job(job_id)
                return
            self._complete_job(
                job_id,
                {
                    "provider": "civitai",
                    "url": url,
                    "paths": [output_path],
                },
            )
        except Exception as exc:
            self._fail_job(job_id, str(exc))
        finally:
            self._forget_job(job_id)

    def _run_url_download_job(
        self,
        job_id: str,
        cancel_event: threading.Event,
        url: str,
        output_dir: str,
        filename: str,
        extract_zip: bool,
    ) -> None:
        """Run one generic URL download, optionally extracting a ZIP."""
        self._update_job(job_id, 0.0, JobStatus.RUNNING)
        output_root = Path(output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        output_path = output_root / filename
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
            self._update_job(job_id, current_progress, JobStatus.RUNNING)
            self._record_file_progress(
                job_id,
                filename,
                downloaded,
                total,
            )

        try:
            completed = download_civitai_file(
                url,
                output_path,
                0,
                progress_callback=progress,
                cancel_callback=cancel_event.is_set,
            )
            if not completed or cancel_event.is_set():
                self._cancel_job(job_id)
                return
            if extract_zip:
                self._record_log_message(job_id, f"Extracting {filename}...")
                with zipfile.ZipFile(output_path, "r") as archive:
                    safe_extract_zip(archive, output_root)
                output_path.unlink(missing_ok=True)
                paths = [output_dir]
            else:
                paths = [str(output_path)]
            self._complete_job(
                job_id,
                {
                    "provider": "url",
                    "url": url,
                    "paths": paths,
                },
            )
        except Exception as exc:
            self._fail_job(job_id, str(exc))
        finally:
            self._forget_job(job_id)
