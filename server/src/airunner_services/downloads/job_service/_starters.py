"""Async job-start entry points for :class:`DownloadJobService`.

The ``start_*`` coroutines resolve and normalize their target paths,
build the job metadata, and hand off to :meth:`_start_job`, which
spawns the matching background runner from the sibling runner mixins.
"""

from __future__ import annotations

import os
import threading
from dataclasses import replace
from typing import Any, Callable

from airunner_services.config.local_settings_store import get_setting
from airunner_services.downloads.huggingface import (
    prepare_huggingface_download_request,
)
from airunner_services.downloads.job_service._helpers import (
    _default_hf_output_dir,
    _download_filename,
)
from airunner_services.runtimes.file_policy import normalize_local_path
from airunner_services.settings import MODELS_DIR


class DownloadJobStartersMixin:
    """Create and start download jobs from the public entry points."""

    async def start_huggingface_download(
        self,
        repo_id: str,
        *,
        model_type: str = "llm",
        output_dir: str | None = None,
        missing_files: list[str] | None = None,
        gguf_filename: str | None = None,
        prefer_pre_quantized: bool = True,
    ) -> str:
        """Create and start one HuggingFace download job."""
        request = prepare_huggingface_download_request(
            repo_id=repo_id,
            model_type=model_type,
            output_dir=output_dir,
            missing_files=missing_files,
            gguf_filename=gguf_filename,
            prefer_pre_quantized=prefer_pre_quantized,
        )
        resolved_output_dir = request.output_dir or _default_hf_output_dir(
            request.repo_id,
            request.model_type,
        )
        normalized_request = replace(
            request,
            output_dir=normalize_local_path(
                resolved_output_dir,
                label="Download output directory",
            ),
        )
        metadata = {
            "provider": "huggingface",
            "repo_id": normalized_request.repo_id,
            "model_type": normalized_request.model_type,
        }
        return await self._start_job(
            metadata,
            self._run_huggingface_job,
            normalized_request,
        )

    async def start_huggingface_file_download(
        self,
        repo_id: str,
        filename: str,
        *,
        output_dir: str,
    ) -> str:
        """Create and start one single-file HuggingFace download job."""
        normalized_output_dir = normalize_local_path(
            output_dir,
            label="Download output directory",
        )
        metadata = {
            "provider": "huggingface",
            "repo_id": repo_id,
            "filename": filename,
        }
        return await self._start_job(
            metadata,
            self._run_huggingface_file_job,
            repo_id,
            filename,
            normalized_output_dir,
        )

    async def start_civitai_model_download(
        self,
        url: str,
        *,
        output_dir: str | None = None,
        api_key: str | None = None,
    ) -> str:
        """Create and start one CivitAI model download job."""
        resolved_output_dir = normalize_local_path(
            output_dir or os.path.join(MODELS_DIR, "art/models/civitai"),
            label="Download output directory",
        )
        metadata = {"provider": "civitai", "url": url}
        return await self._start_job(
            metadata,
            self._run_civitai_model_job,
            url,
            resolved_output_dir,
            api_key or get_setting("civitai/api_key", ""),
        )

    async def start_civitai_file_download(
        self,
        url: str,
        *,
        output_path: str,
        file_size: int,
        api_key: str | None = None,
    ) -> str:
        """Create and start one CivitAI single-file download job."""
        normalized_output_path = normalize_local_path(
            output_path,
            label="Download file path",
        )
        metadata = {"provider": "civitai", "url": url}
        return await self._start_job(
            metadata,
            self._run_civitai_file_job,
            url,
            normalized_output_path,
            max(0, int(file_size)),
            api_key or get_setting("civitai/api_key", ""),
        )

    async def start_url_download(
        self,
        url: str,
        *,
        output_dir: str,
        filename: str | None = None,
        extract_zip: bool = False,
    ) -> str:
        """Create and start one generic URL download job."""
        normalized_output_dir = normalize_local_path(
            output_dir,
            label="Download output directory",
        )
        resolved_filename = filename or _download_filename(url)
        metadata = {"provider": "url", "url": url}
        return await self._start_job(
            metadata,
            self._run_url_download_job,
            url,
            normalized_output_dir,
            resolved_filename,
            extract_zip,
        )

    async def start_nltk_download(self, data_names: list[str]) -> str:
        """Create and start one NLTK data download job."""
        resolved_names = [
            name.strip() for name in data_names if str(name).strip()
        ]
        if not resolved_names:
            raise ValueError("At least one NLTK data name is required")
        metadata = {
            "provider": "nltk",
            "data_names": resolved_names,
        }
        return await self._start_job(
            metadata,
            self._run_nltk_download_job,
            resolved_names,
        )

    async def _start_job(
        self,
        metadata: dict[str, Any],
        runner: Callable[..., None],
        *args: Any,
    ) -> str:
        """Create one tracked job and start its background runner."""
        job_id = await self._tracker.create_job(metadata=metadata)
        cancel_event = threading.Event()
        thread = threading.Thread(
            target=runner,
            args=(job_id, cancel_event, *args),
            daemon=True,
        )
        with self._lock:
            self._cancel_events[job_id] = cancel_event
            self._threads[job_id] = thread
        thread.start()
        return job_id
