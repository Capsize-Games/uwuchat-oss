"""Distributed, Redis-backed priority-lane rate limiter for OpenRouter.

Provides a counting semaphore with two static priority lanes (live/bulk)
per resource (embedding/completion), plus per-tenant sub-caps within each
lane.  Uses Redis sorted sets with TTL-scored members so slots
self-heal if a worker crashes without releasing.

Modeled on the Lua-script idiom established in
``projects/uwuchat/server/email/sync_mailbox_lock.py``, but as a
counting semaphore (N concurrent holders) rather than a mutex (1).

See ``plans/uwuchat-embedding-rate-limit-priority-lanes.md`` for the
full design rationale.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Literal

from airunner_services.tasks.redis_client import cache_redis

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  Configuration (environment-overridable defaults)                   #
# ------------------------------------------------------------------ #

_EMBEDDING_LIVE_MAX = int(
    os.environ.get(
        "EMBEDDING_LIVE_MAX_CONCURRENT", "30",
    ),
)
_EMBEDDING_BULK_MAX = int(
    os.environ.get(
        "EMBEDDING_BULK_MAX_CONCURRENT", "150",
    ),
)
_COMPLETION_LIVE_MAX = int(
    os.environ.get(
        "COMPLETION_LIVE_MAX_CONCURRENT", "40",
    ),
)
_COMPLETION_BULK_MAX = int(
    os.environ.get(
        "COMPLETION_BULK_MAX_CONCURRENT", "30",
    ),
)

# Fraction of the lane budget any single tenant may consume at once.
# 0.3 = 30% of the lane max.  Configurable per resource + lane.
_BULK_TENANT_FRACTION = float(
    os.environ.get(
        "BULK_TENANT_MAX_FRACTION", "0.3",
    ),
)
_LIVE_TENANT_FRACTION = float(
    os.environ.get(
        "LIVE_TENANT_MAX_FRACTION", "0.5",
    ),
)

# How long a slot lease lasts before the sorted-set self-healing
# reclaims it.  Must comfortably exceed the slowest expected API call
# (embedding: ~30 s timeout + retry backoff up to ~60 s;
# completion: 120 s request_timeout).  A 300 s lease gives generous
# headroom for both without leaking slots for long.
_LEASE_TTL_SECONDS = int(
    os.environ.get(
        "LIMITER_LEASE_TTL_SECONDS", "300",
    ),
)

# How long a live-priority caller waits (polling) before giving up.
_LIVE_WAIT_POLL_SECONDS = 0.25
_LIVE_WAIT_MAX_SECONDS = float(
    os.environ.get(
        "LIVE_WAIT_MAX_SECONDS", "3.0",
    ),
)

# ------------------------------------------------------------------ #
#  Resource definitions                                               #
# ------------------------------------------------------------------ #

Resource = Literal["embedding", "completion"]
Lane = Literal["live", "bulk"]


def _lane_max(resource: Resource, lane: Lane) -> int:
    """Return the configured lane budget for *resource*/*lane*."""
    if resource == "embedding":
        return (
            _EMBEDDING_LIVE_MAX if lane == "live"
            else _EMBEDDING_BULK_MAX
        )
    return (
        _COMPLETION_LIVE_MAX if lane == "live"
        else _COMPLETION_BULK_MAX
    )


def _tenant_max(resource: Resource, lane: Lane) -> int:
    """Return the per-tenant sub-cap for *resource*/*lane*."""
    fraction = (
        _LIVE_TENANT_FRACTION if lane == "live"
        else _BULK_TENANT_FRACTION
    )
    return max(1, int(_lane_max(resource, lane) * fraction))


def _lane_key(resource: Resource, lane: Lane) -> str:
    """Redis sorted-set key for the lane."""
    return f"airunner:limiter:{resource}:{lane}"


def _tenant_count_key(
    resource: Resource, lane: Lane, tenant_key: str,
) -> str:
    """Redis counter key for one tenant's active slots in a lane."""
    return f"airunner:limiter:{resource}:{lane}:tenant:{tenant_key}"


# ------------------------------------------------------------------ #
#  Lua scripts (atomic, evaluated server-side)                        #
# ------------------------------------------------------------------ #

# Acquire one slot:
#   1. Evict expired members (score < now).
#   2. If lane is at capacity → return nil.
#   3. If tenant is at its sub-cap → return nil.
#   4. Add member, increment tenant counter, return token.
#
# KEYS[1] = lane sorted-set key
# KEYS[2] = tenant counter key
# ARGV[1] = member token (UUID)
# ARGV[2] = expiry score (now + lease_ttl)
# ARGV[3] = lane max concurrent
# ARGV[4] = tenant max concurrent
# ARGV[5] = lease TTL (for the tenant counter key expiry)

_ACQUIRE_SCRIPT = """
local now = tonumber(redis.call("TIME")[1])
redis.call("ZREMRANGEBYSCORE", KEYS[1], "-inf", now)

local count = redis.call("ZCARD", KEYS[1])
local lane_max = tonumber(ARGV[3])
if count >= lane_max then
    return nil
end

local tenant_count = tonumber(redis.call("GET", KEYS[2]) or "0")
local tenant_max = tonumber(ARGV[4])
if tenant_count >= tenant_max then
    return nil
end

local score = tonumber(ARGV[2])
redis.call("ZADD", KEYS[1], score, ARGV[1])
redis.call("INCR", KEYS[2])
redis.call("EXPIRE", KEYS[2], tonumber(ARGV[5]))
return ARGV[1]
"""

# Release one slot:
#   1. Remove the member (safe if already expired).
#   2. Decrement the tenant counter (floor at 0).
#
# KEYS[1] = lane sorted-set key
# KEYS[2] = tenant counter key
# ARGV[1] = member token

_RELEASE_SCRIPT = """
redis.call("ZREM", KEYS[1], ARGV[1])
local v = tonumber(redis.call("GET", KEYS[2]) or "1")
if v > 0 then
    redis.call("DECR", KEYS[2])
end
return 1
"""


# ------------------------------------------------------------------ #
#  Public API                                                         #
# ------------------------------------------------------------------ #


class AcquiredSlot:
    """Opaque token representing an acquired concurrency slot.

    Call ``release()`` when the work is done, or let the instance
    fall out of scope — the lease expires on its own if ``release()``
    is never called (process crash / unhandled exception).
    """

    def __init__(
        self,
        token: str,
        resource: Resource,
        lane: Lane,
        tenant_key: str,
    ) -> None:
        self._token = token
        self._resource = resource
        self._lane = lane
        self._tenant_key = tenant_key
        self._released = False

    def release(self) -> None:
        """Release this slot back to the pool.  Idempotent."""
        if self._released:
            return
        self._released = True
        try:
            r = cache_redis()
            r.eval(
                _RELEASE_SCRIPT,
                2,
                _lane_key(self._resource, self._lane),
                _tenant_count_key(
                    self._resource, self._lane, self._tenant_key,
                ),
                self._token,
            )
        except Exception:
            logger.debug(
                "Failed to release limiter slot %s (may have expired)",
                self._token,
            )


def acquire_slot(
    resource: Resource,
    lane: Lane,
    tenant_key: str,
) -> AcquiredSlot | None:
    """Attempt to acquire one concurrency slot.

    Returns an ``AcquiredSlot`` on success, or ``None`` if the lane
    (or the tenant's sub-cap within it) is at capacity.  The caller
    must call ``slot.release()`` when done; the lease self-expires
    if ``release()`` is never called.

    *tenant_key* may be empty ("") for call sites where tenant context
    is genuinely unavailable; per-tenant capping is skipped in that
    case (the tenant counter key is still passed but no sub-cap is
    enforced — the lane-level cap still applies).
    """
    r = cache_redis()
    token = str(uuid.uuid4())
    now = int(time.time())
    score = now + _LEASE_TTL_SECONDS
    lane_max = _lane_max(resource, lane)
    tenant_max = _tenant_max(resource, lane)

    if not tenant_key:
        # No tenant context — skip per-tenant sub-cap by setting it
        # to the lane max (effectively unbounded per-tenant).
        tenant_max = lane_max

    try:
        result = r.eval(
            _ACQUIRE_SCRIPT,
            2,
            _lane_key(resource, lane),
            _tenant_count_key(resource, lane, tenant_key),
            token,
            score,
            lane_max,
            tenant_max,
            _LEASE_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "Limiter acquire eval failed for %s/%s: %s",
            resource, lane, exc,
        )
        return None

    if result is None:
        return None

    return AcquiredSlot(
        token=str(result),
        resource=resource,
        lane=lane,
        tenant_key=tenant_key,
    )


def acquire_with_retry(
    resource: Resource,
    lane: Lane,
    tenant_key: str,
    *,
    max_wait: float = _LIVE_WAIT_MAX_SECONDS,
    poll_interval: float = _LIVE_WAIT_POLL_SECONDS,
) -> AcquiredSlot | None:
    """Acquire a slot, waiting up to *max_wait* seconds.

    For live-lane callers: short bounded wait before degrading.
    For bulk-lane callers: pass a larger *max_wait* to let the
    existing retry/backoff logic drive the retry loop instead.
    """
    deadline = time.monotonic() + max_wait
    while True:
        slot = acquire_slot(resource, lane, tenant_key)
        if slot is not None:
            return slot
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(poll_interval, remaining))


def lane_stats(resource: Resource, lane: Lane) -> dict:
    """Return current occupancy and capacity for a lane (diagnostic)."""
    try:
        r = cache_redis()
        key = _lane_key(resource, lane)
        now = int(time.time())
        r.zremrangebyscore(key, "-inf", now)
        count = r.zcard(key) or 0
        return {
            "resource": resource,
            "lane": lane,
            "active": int(count),
            "max": _lane_max(resource, lane),
        }
    except Exception:
        return {
            "resource": resource,
            "lane": lane,
            "active": 0,
            "max": _lane_max(resource, lane),
        }
