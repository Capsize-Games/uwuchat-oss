"""GPU inference-mode switch Celery task.

Enqueued (fire-and-forget) from ``code_mode_service.set_code_mode`` so
the WebSocket RPC toggle returns immediately — the actual daemon
stop/start (multi-second) happens asynchronously on the Celery worker.

The task is intentionally dumb: it just calls
``gpu_inference_mode.apply_code_mode(enabled)`` and logs the outcome.
The DIALOGUE routing check (Decision B) reads the persisted
``conversation.user_data["code_mode"]`` state directly, so a chat
message arriving while the switch is still in flight simply uses the
model matching the *new* target state once the daemon is ready — the
switch itself self-heals.

Retry policy: a failed switch retries a few times with a short
countdown — the realistic failure modes (docker socket briefly
unavailable, container mid-restart) are transient.
"""

from __future__ import annotations

from airunner_services.tasks.celery_app import app
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@app.task(
    bind=True,
    name=(
        "projects.uwuchat.server.tasks.gpu_inference_tasks."
        "apply_code_mode_gpu_switch"
    ),
    max_retries=3,
    default_retry_delay=15,
    acks_late=True,
)
def apply_code_mode_gpu_switch(self, enabled: bool) -> dict:
    """Apply the GPU daemon state for the target code-mode state.

    Code mode ON  → code daemon loaded, chat daemon stopped.
    Code mode OFF → chat daemon loaded, code daemon stopped.

    Returns ``{"status": "ok" | "error", ...}`` — never raises past the
    retry budget (a final failure is logged and swallowed so a switch
    failure cannot wedge the Celery worker).
    """
    from projects.uwuchat.server import gpu_inference_mode

    try:
        ok = gpu_inference_mode.apply_code_mode(enabled)
    except Exception:
        logger.exception("GPU switch (enabled=%s) failed", enabled)
        raise self.retry()

    if ok:
        logger.info(
            "GPU switch applied: code_mode=%s (%s)",
            enabled, gpu_inference_mode.current_mode_description(),
        )
        return {"status": "ok", "code_mode": enabled}

    # apply_code_mode never raises — a False return means the target
    # state wasn't reached. Retry a couple of times (transient docker
    # API hiccups), then report the failure.
    attempt = (self.request.retries or 0) + 1
    if attempt < self.max_retries:
        raise self.retry(countdown=self.default_retry_delay)
    logger.error(
        "GPU switch (enabled=%s) could not reach target state after "
        "%d attempts: %s",
        enabled, attempt, gpu_inference_mode.current_mode_description(),
    )
    return {"status": "error", "code_mode": enabled}


__all__ = ["apply_code_mode_gpu_switch"]
