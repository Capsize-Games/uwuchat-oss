"""Per-mailbox execution lock guarding the shared progress counter.

``_sync_one_mailbox`` runs with ``task_acks_late=True`` and no task
time limit or broker visibility-timeout override, so for a large,
slow mailbox Celery's Redis broker can consider the still-running
task abandoned and redeliver it — starting a second, fully
independent execution for the same mailbox while the first is still
in flight. ``EmailSyncCheckpoint`` resumption means the *data* stays
correct either way (duplicate fetches are deduped on write), but both
executions call ``emit_progress_delta`` for overlapping message
ranges, inflating the shared account-wide ``current`` counter past
``total``. This lock lets a redelivered execution detect the
collision and skip, instead of double-counting.
"""

from __future__ import annotations

from airunner_services.tasks.redis_client import cache_redis

_LOCK_TTL_SECONDS = 3600
_LOCK_PREFIX = "email_sync_mailbox_lock:"

_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


def _lock_key(email_account_id: int, mailbox_id: str) -> str:
    return f"{_LOCK_PREFIX}{email_account_id}:{mailbox_id}"


def acquire_mailbox_lock(
    email_account_id: int, mailbox_id: str, token: str,
) -> bool:
    """Claim *mailbox_id* for this task execution (*token*).

    Returns False if another execution already holds the lock — the
    caller should skip work rather than double-count progress.
    """
    r = cache_redis()
    key = _lock_key(email_account_id, mailbox_id)
    return bool(r.set(key, token, nx=True, ex=_LOCK_TTL_SECONDS))


def release_mailbox_lock(
    email_account_id: int, mailbox_id: str, token: str,
) -> None:
    """Release the lock, but only if still owned by *token*.

    Atomic compare-and-delete (Lua script) so a stale execution that
    outlived the TTL can't release a lock a newer execution has since
    acquired.
    """
    r = cache_redis()
    key = _lock_key(email_account_id, mailbox_id)
    r.eval(_RELEASE_SCRIPT, 1, key, token)


__all__ = ["acquire_mailbox_lock", "release_mailbox_lock"]
