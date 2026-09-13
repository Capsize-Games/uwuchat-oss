"""Download job Celery task wrappers.

Replaces raw ``threading.Thread`` spawns in ``job_service.py``
with Celery ``AbortableTask`` tasks.  The existing
``PersistentJobTracker`` remains for durable state; Celery
adds process isolation, concurrency capping, and cancel support.
"""

from __future__ import annotations


from celery.utils.log import get_task_logger

from airunner_services.tasks.celery_app import app

logger = get_task_logger(__name__)


@app.task(
    bind=True,
    name="airunner_services.tasks.download_tasks.huggingface_download",
    queue="downloads",
    max_retries=1,
)
def huggingface_download(self, repo_id: str, **kwargs) -> dict:
    """Download a model from HuggingFace.

    Enqueued by ``DownloadJobService`` instead of spawning a raw
    thread.  The caller is responsible for job-state tracking and
    progress updates.
    """
    # NOTE: not yet wired.  DownloadJobService._run_huggingface_job
    # (job_service.py:111) does the actual download work; this Celery
    # task is a stub awaiting the migration from in-process threads to
    # Celery workers.  To wire, import and call _run_huggingface_job
    # directly within this task body.
    logger.info(
        "HF download task stub: repo=%s (not yet wired)", repo_id,
    )
    return {"status": "not_implemented", "repo_id": repo_id}


@app.task(
    bind=True,
    name=(
        "airunner_services.tasks.download_tasks.civitai_model_download"
    ),
    queue="downloads",
    max_retries=1,
)
def civitai_model_download(
    self, url: str, output_dir: str, **kwargs
) -> dict:
    """Download a CivitAI model."""
    logger.info(
        "CivitAI download task stub: url=%s (not yet wired)", url,
    )
    return {"status": "not_implemented", "url": url}
