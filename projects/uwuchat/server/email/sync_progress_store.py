"""Account-scoped, cross-process email-sync progress store (Redis DB 3).

Email sync runs as Celery tasks in a separate worker process from the
API server, so progress cannot be pushed over the in-process
``WsEventBus``. This store is the cross-process-safe replacement: one
Redis hash per ``email_account_id``, polled by an authenticated
endpoint instead of pushed over a WebSocket.

Unlike ``job_progress_*`` in the shared ``redis_client`` module (keyed
by Celery task ID, read by the admin job UI), this is keyed by
``email_account_id`` and read by that account's own owner.

The whole account's sync is represented by a *single* progress bar,
not one per mailbox — with 30+ mailboxes on a real account, one bar
each is an unreadable wall of bars. Backfill (concurrent, one Celery
task per mailbox) reports via ``email_sync_progress_increment``, which
atomically bumps a shared counter (``HINCRBY``) rather than each
mailbox owning its own slot. Sequential phases (contacts,
summarization, co-occurrence — each running inside a single task, not
concurrently) use ``email_sync_progress_write`` instead, which sets
an absolute current/total for whatever phase is running now.
"""

from __future__ import annotations

from typing import Any

from airunner_services.tasks.redis_client import cache_redis

EMAIL_SYNC_PROGRESS_TTL_SECONDS = 600  # 10 minutes, refreshed per write
EMAIL_SYNC_COMPLETE_TTL_SECONDS = 120  # grace period after completion

_EMAIL_SYNC_PREFIX = "email_sync:"


def email_sync_progress_key(email_account_id: int) -> str:
    """Return the Redis hash key for one account's sync progress."""
    return f"{_EMAIL_SYNC_PREFIX}{email_account_id}"


def email_sync_progress_start(email_account_id: int) -> None:
    """Reset an account's progress hash at the start of a new sync run.

    Must be called before any progress write for this run, so a poll
    landing between "connect" and the first mailbox progress event
    sees a fresh active state instead of the previous run's stale
    completion.
    """
    r = cache_redis()
    key = email_sync_progress_key(email_account_id)
    pipe = r.pipeline()
    pipe.delete(key)
    pipe.hset(key, mapping={
        "active": "1", "current": "0", "total": "0",
        "label": "Starting analysis…", "unit": "messages",
        "success": "", "message": "",
    })
    pipe.expire(key, EMAIL_SYNC_PROGRESS_TTL_SECONDS)
    pipe.execute()


def email_sync_progress_set_total(
    email_account_id: int, total: int, label: str,
) -> None:
    """Set the known total upfront (e.g. summed across all mailboxes
    before backfill starts), so the bar shows a real percentage from
    the first update instead of growing denominator guesswork."""
    r = cache_redis()
    key = email_sync_progress_key(email_account_id)
    pipe = r.pipeline()
    pipe.hset(key, mapping={
        "active": "1", "total": str(total), "label": label,
    })
    pipe.expire(key, EMAIL_SYNC_PROGRESS_TTL_SECONDS)
    pipe.execute()


def email_sync_progress_increment(
    email_account_id: int,
    delta: int,
    label: str,
    unit: str = "messages",
) -> None:
    """Atomically bump the shared counter by *delta*.

    Used by concurrent per-mailbox backfill tasks — HINCRBY is safe
    under concurrent writers, unlike a read-current/write-current
    round trip, which would lose updates under a race.
    """
    r = cache_redis()
    key = email_sync_progress_key(email_account_id)
    pipe = r.pipeline()
    pipe.hincrby(key, "current", delta)
    pipe.hset(key, mapping={"active": "1", "label": label, "unit": unit})
    pipe.expire(key, EMAIL_SYNC_PROGRESS_TTL_SECONDS)
    pipe.execute()


def email_sync_progress_write(
    email_account_id: int,
    label: str,
    current: int,
    total: int,
    unit: str = "messages",
) -> None:
    """Set an absolute current/total — for sequential (non-concurrent)
    phases, e.g. contact extraction, summarization, co-occurrence."""
    r = cache_redis()
    key = email_sync_progress_key(email_account_id)
    pipe = r.pipeline()
    pipe.hset(key, mapping={
        "active": "1",
        "current": str(current),
        "total": str(total),
        "label": label,
        "unit": unit,
    })
    pipe.expire(key, EMAIL_SYNC_PROGRESS_TTL_SECONDS)
    pipe.execute()


def email_sync_complete_write(
    email_account_id: int,
    success: bool,
    message: str,
) -> None:
    """Write the terminal state.

    Keeps the hash around (short TTL) so a poll racing the last
    progress update still observes the final success/failure state
    at least once before it expires.
    """
    r = cache_redis()
    key = email_sync_progress_key(email_account_id)
    pipe = r.pipeline()
    pipe.hset(key, mapping={
        "active": "0",
        "success": "1" if success else "0",
        "message": message,
    })
    pipe.expire(key, EMAIL_SYNC_COMPLETE_TTL_SECONDS)
    pipe.execute()


def email_sync_progress_read(email_account_id: int) -> dict[str, Any]:
    """Read the current sync-progress state for one account.

    Returns the idle shape (``active: False``) when no sync has ever
    run or the record has expired. ``progress`` is always computed
    here from current/total, never stored, so the two write paths
    (absolute vs. incremental) can't drift out of sync with it.
    """
    r = cache_redis()
    data = r.hgetall(email_sync_progress_key(email_account_id))
    if not data:
        return {
            "active": False, "current": 0, "total": 0, "progress": 0,
            "label": "", "unit": "messages",
            "success": None, "message": "",
        }
    current = int(data.get("current", 0) or 0)
    total = int(data.get("total", 0) or 0)
    progress = int((current / total) * 100) if total else 0
    success_raw = data.get("success", "")
    return {
        "active": data.get("active") == "1",
        "current": current,
        "total": total,
        "progress": progress,
        "label": data.get("label", ""),
        "unit": data.get("unit", "messages"),
        "success": (
            None if success_raw == "" else success_raw == "1"
        ),
        "message": data.get("message", ""),
    }
