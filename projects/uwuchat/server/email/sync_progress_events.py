"""Progress-reporting helpers shared by every phase of the sync
pipeline (backfill, contact extraction, co-occurrence graph,
summarization) so the client sees one continuous progress bar
across the whole job — a single bar, not one per mailbox.

Writes to the account-scoped Redis store in ``sync_progress_store``
rather than the in-process ``WsEventBus`` — email sync runs as Celery
tasks in a worker process separate from the API server, so a
WebSocket broadcast made here would only reach that worker's own
(subscriber-less) event-bus singleton and never the browser. See
``sync_progress_store`` for the cross-process-safe replacement.
"""

from __future__ import annotations

from .sync_progress_store import (
    email_sync_complete_write,
    email_sync_progress_increment,
    email_sync_progress_write,
)


def emit_progress(
    email_account_id: int,
    label: str,
    current: int,
    total: int,
    unit: str = "messages",
) -> None:
    """Set an absolute progress update for *email_account_id*.

    For sequential phases (contact extraction, summarization,
    co-occurrence) that run once, inside a single task — not
    concurrently — so an absolute current/total is safe. *label* is
    the human-readable current step, e.g. "Summarizing threads".
    *total* of 0 renders as an indeterminate step.
    """
    email_sync_progress_write(
        email_account_id, label, current, total, unit=unit,
    )


def emit_progress_delta(
    email_account_id: int,
    delta: int,
    label: str,
    unit: str = "messages",
) -> None:
    """Bump the shared progress counter by *delta*.

    For the concurrent mailbox-backfill phase — multiple Celery tasks
    report at once, so each contributes its newly-processed count to
    one shared total instead of owning its own bar.
    """
    email_sync_progress_increment(
        email_account_id, delta, label, unit=unit,
    )


def emit_complete(
    email_account_id: int, success: bool, message: str,
) -> None:
    """Record one terminal sync result for *email_account_id*."""
    email_sync_complete_write(email_account_id, success, message)


__all__ = ["emit_progress", "emit_progress_delta", "emit_complete"]
