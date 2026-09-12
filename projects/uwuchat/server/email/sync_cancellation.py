"""Cooperative cancellation for in-flight email sync jobs.

Disconnecting an account mid-sync must stop the sync promptly —
otherwise it keeps writing rows for an account whose data was just
cascade-deleted, undermining the purge-on-disconnect guarantee. The
sync pipeline checks ``is_cancelled()`` between units of work
(backfill pages, mailboxes, message chunks) so it notices within one
unit's processing time rather than running to completion.

Backed by Redis, not an in-process set — ``cancel_sync()`` is called
from ``_do_disconnect`` in the API server process, while
``is_cancelled()`` is checked inside the Celery sync tasks, which run
in a separate worker process. An in-process flag would never be seen
across that boundary (the same class of bug the progress bar had —
see ``sync_progress_store``).
"""

from __future__ import annotations

from airunner_services.tasks.redis_client import cache_redis

_CANCEL_TTL_SECONDS = 3600  # safety valve if finish_sync is ever missed
_CANCEL_PREFIX = "email_sync_cancel:"


def _cancel_key(email_account_id: int) -> str:
    return f"{_CANCEL_PREFIX}{email_account_id}"


def start_sync(email_account_id: int) -> None:
    """Clear any stale cancellation flag when a new sync begins."""
    cache_redis().delete(_cancel_key(email_account_id))


def cancel_sync(email_account_id: int) -> None:
    """Signal any in-flight sync for this account to stop."""
    cache_redis().setex(
        _cancel_key(email_account_id), _CANCEL_TTL_SECONDS, "1",
    )


def is_cancelled(email_account_id: int) -> bool:
    """Return whether a running sync for this account should stop."""
    return bool(cache_redis().exists(_cancel_key(email_account_id)))


def finish_sync(email_account_id: int) -> None:
    """Clear the cancellation flag once a sync job ends."""
    cache_redis().delete(_cancel_key(email_account_id))


__all__ = [
    "start_sync", "cancel_sync", "is_cancelled", "finish_sync",
]
