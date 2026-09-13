"""Redis client wrapper — per-DB-index access with sane defaults.

Each DB index maps to a conceptual service boundary, mirroring the
numbering from the architecture plan's Part 2:

    DB 0 — Celery broker
    DB 1 — Celery result backend
    DB 2 — DEK relay (short TTL, read-once security primitive)
    DB 3 — General cache (weather/geocoding) + job-progress mirror

The DEK relay and job-progress helpers are thin wrappers around the
Redis connection to enforce the access pattern (get-then-delete for
DEK relay, HSET+TTL for job progress) rather than exposing raw SET/GET.
"""

from __future__ import annotations

import functools
import os
from typing import Any

_REDIS_URL = os.environ.get(
    "AIRUNNER_REDIS_URL",
    "redis://airunner-redis:6379",
)


# -- Per-DB connection factories --------------------------------------------


@functools.lru_cache(maxsize=None)
def _redis_db(db: int):
    """Return a Redis client scoped to *db*, cached per process.

    ``redis.Redis`` instances are thread-safe and hold their own
    internal connection pool — building a fresh client (and thus a
    fresh TCP connection) on every call, as this used to do, exhausts
    the container's ephemeral port range under any sustained call
    volume (e.g. per-thread progress writes while indexing a large
    mailbox). Caching by *db* means every caller for the same DB
    index shares one pool instead.
    """
    import redis

    return redis.Redis.from_url(
        _REDIS_URL,
        db=db,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_keepalive=True,
        health_check_interval=30,
    )


def broker_redis():
    """DB 0 — Celery broker (used internally by Celery, not by app code)."""
    return _redis_db(0)


def result_backend_redis():
    """DB 1 — Celery result backend."""
    return _redis_db(1)


def dek_relay_redis():
    """DB 2 — DEK relay (read-once, short TTL)."""
    return _redis_db(2)


def cache_redis():
    """DB 3 — General cache + job-progress mirror."""
    return _redis_db(3)


# -- DEK relay helpers (Part 3) ---------------------------------------------

DEK_RELAY_TTL_SECONDS = 600  # 10 minutes (shorter than in-process cache)

_DEK_RELAY_KEY_PREFIX = "dek_relay:"


def _dek_relay_key(account_id: int) -> str:
    """Return the Redis key for an account's wrapped DEK."""
    return f"{_DEK_RELAY_KEY_PREFIX}{account_id}"


def dek_relay_store(account_id: int, wrapped_dek: str) -> None:
    """Store a wrapped DEK in the relay with a short, non-renewable TTL.

    *wrapped_dek* must be the DEK encrypted with the global keyring
    (see ``task_helpers.wrap_dek_for_relay``).  Only call this *after*
    the task has been successfully enqueued (the relay serves the
    Celery worker, not arbitrary readers).
    """
    r = dek_relay_redis()
    r.setex(
        _dek_relay_key(account_id),
        DEK_RELAY_TTL_SECONDS,
        wrapped_dek,
    )


def dek_relay_get(account_id: int) -> str | None:
    """Read the wrapped DEK for *account_id* without deleting it.

    For multi-task pipelines (e.g. a Celery chord: one parent task,
    N per-item children, one callback) where more than one task
    invocation needs the same relay entry — ``dek_relay_get_and_delete``
    would only serve the first consumer and leave every later one with
    no DEK. Callers using this must explicitly call
    ``dek_relay_delete`` once the *whole* pipeline finishes; until
    then the entry is still bounded by its TTL.
    """
    r = dek_relay_redis()
    return r.get(_dek_relay_key(account_id))


def dek_relay_get_and_delete(account_id: int) -> str | None:
    """Read and immediately delete the wrapped DEK for *account_id*.

    Read-once semantics — this is a one-time hand-off token, not a
    cache to poll.  Returns None when no entry exists (the task
    must handle the skip-and-defer path described in Part 3).
    """
    r = dek_relay_redis()
    key = _dek_relay_key(account_id)
    # GET + DEL as a pipeline for atomicity.
    pipe = r.pipeline()
    pipe.get(key)
    pipe.delete(key)
    result = pipe.execute()
    return result[0]  # GET result (str or None)


def dek_relay_delete(account_id: int) -> None:
    """Explicitly remove a DEK relay entry (e.g. on task cancellation)."""
    r = dek_relay_redis()
    r.delete(_dek_relay_key(account_id))


# -- Job-progress helpers (Part 4) ------------------------------------------

JOB_PROGRESS_TTL_SECONDS = 86400  # 24 hours

_JOB_PREFIX = "job:"
_TENANT_JOBS_PREFIX = "tenant_jobs:"


def job_progress_key(job_id: str) -> str:
    """Return the Redis key for a single job's progress hash."""
    return f"{_JOB_PREFIX}{job_id}"


def tenant_jobs_key(tenant_key: str) -> str:
    """Return the Redis key for a tenant's set of job IDs."""
    return f"{_TENANT_JOBS_PREFIX}{tenant_key}"


def job_progress_write(
    job_id: str,
    status: str,
    current: int = 0,
    total: int = 0,
    label: str = "",
    tenant_key: str = "",
    error: str = "",
) -> None:
    """Write or update a job's progress in Redis.

    Also adds *job_id* to the per-tenant index so the admin UI can
    enumerate all jobs for a given tenant without scanning all keys.
    """
    r = cache_redis()
    data: dict[str, str] = {
        "status": status,
        "current": str(current),
        "total": str(total),
        "label": label,
        "error": error,
    }
    key = job_progress_key(job_id)
    pipe = r.pipeline()
    pipe.hset(key, mapping=data)  # type: ignore[arg-type]
    pipe.expire(key, JOB_PROGRESS_TTL_SECONDS)
    if tenant_key:
        pipe.sadd(tenant_jobs_key(tenant_key), job_id)
        pipe.expire(
            tenant_jobs_key(tenant_key),
            JOB_PROGRESS_TTL_SECONDS,
        )
    pipe.execute()


def job_progress_read(job_id: str) -> dict[str, Any] | None:
    """Read one job's progress hash. Returns None if not found."""
    r = cache_redis()
    data = r.hgetall(job_progress_key(job_id))
    if not data:
        return None
    return {
        "job_id": job_id,
        "status": data.get("status", ""),
        "current": int(data.get("current", 0)),
        "total": int(data.get("total", 0)),
        "label": data.get("label", ""),
        "error": data.get("error", ""),
    }


def job_progress_list_for_tenant(
    tenant_key: str,
) -> list[dict[str, Any]]:
    """Return all job-progress records for *tenant_key*."""
    r = cache_redis()
    job_ids = r.smembers(tenant_jobs_key(tenant_key))
    results: list[dict[str, Any]] = []
    for jid in job_ids:
        data = r.hgetall(job_progress_key(jid))
        if data:
            results.append({
                "job_id": jid,
                "status": data.get("status", ""),
                "current": int(data.get("current", 0)),
                "total": int(data.get("total", 0)),
                "label": data.get("label", ""),
                "error": data.get("error", ""),
            })
    return results


def job_progress_delete(job_id: str) -> None:
    """Remove a single job-progress record."""
    r = cache_redis()
    r.delete(job_progress_key(job_id))
