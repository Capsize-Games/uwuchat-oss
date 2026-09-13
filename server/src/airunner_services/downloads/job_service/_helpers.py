"""Module-level helpers shared by the download job mixins.

Holds the path-resolution and progress-reporting helpers that the
original ``job_service.py`` module exposed at module level alongside
``DownloadJobService``.
"""

from __future__ import annotations

import asyncio
import os
from typing import Callable

from airunner_services.downloads.persistent_job_tracker import (
    JobStatus,
    PersistentJobTracker,
)
from airunner_services.settings import MODELS_DIR


def _default_hf_output_dir(repo_id: str, model_type: str) -> str:
    """Return the shared local output directory for one HF model type."""
    model_name = repo_id.split("/")[-1]
    if model_type in {"llm", "gguf"}:
        return os.path.join(MODELS_DIR, "text/models/llm/causallm", model_name)
    if model_type == "art":
        return os.path.join(MODELS_DIR, "art/models", model_name)
    if model_type == "tts":
        return os.path.join(MODELS_DIR, "text/models/tts", model_name)
    if model_type == "stt":
        return os.path.join(MODELS_DIR, "text/models/stt", model_name)
    if model_type == "embedding":
        return os.path.join(
            MODELS_DIR, "text/models/llm/embedding", model_name
        )
    return os.path.join(MODELS_DIR, "models", model_name)


def _coerce_progress(current: int, total: int) -> float:
    """Return one normalized progress percentage."""
    if total <= 0:
        return 0.0
    return max(0.0, min(100.0, (float(current) / float(total)) * 100.0))


def _download_filename(url: str) -> str:
    """Return one filesystem filename derived from a URL path."""
    candidate = url.split("?", 1)[0].rstrip("/").split("/")[-1]
    return candidate or "download.bin"


def _progress_reporter(
    job_id: str,
    tracker: PersistentJobTracker,
) -> Callable[[str, int, int], None]:
    """Return one throttled HF progress callback."""
    last_progress = -1.0

    def report(_filename: str, downloaded: int, total: int) -> None:
        nonlocal last_progress
        progress = _coerce_progress(downloaded, total)
        if progress < 100.0 and progress - last_progress < 1.0:
            return
        last_progress = progress
        asyncio.run(
            tracker.update_progress(job_id, progress, JobStatus.RUNNING)
        )

    return report


def _civitai_progress_reporter(
    job_id: str,
    tracker: PersistentJobTracker,
    completed_bytes: int,
    total_bytes: int,
) -> Callable[[int, int], None]:
    """Return one throttled CivitAI progress callback."""
    last_progress = -1.0

    def report(downloaded: int, total: int) -> None:
        nonlocal last_progress
        overall_total = total_bytes or total
        overall_progress = _coerce_progress(
            completed_bytes + downloaded, overall_total
        )
        if overall_progress < 100.0 and overall_progress - last_progress < 1.0:
            return
        last_progress = overall_progress
        asyncio.run(
            tracker.update_progress(
                job_id, overall_progress, JobStatus.RUNNING
            )
        )

    return report
