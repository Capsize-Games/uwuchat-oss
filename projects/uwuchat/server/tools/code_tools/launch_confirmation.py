"""Server-side confirmation gate for launch_headlesscode_session.

The tool's ``confirmed`` argument is set by the model itself, so it
cannot alone prove a user actually confirmed anything — a model could
set ``confirmed=true`` on its very first call. This module tracks a
real "the user was asked" marker in Redis (short TTL; this is
ephemeral request-flow state, not a durable record, so the general
cache DB is the right fit — same DB `sync_progress_store.py` already
uses for similarly short-lived per-request state).

A ``confirmed=true`` call only proceeds if a matching unconfirmed call
for the exact same (chatbot, project, task) preceded it within the TTL
window; the marker is consumed (deleted) on use, so it cannot be
replayed for a second free launch.
"""

from __future__ import annotations

import hashlib

from airunner_services.tasks.redis_client import cache_redis

_PENDING_CONFIRM_TTL_SECONDS = 900  # 15 minutes


def launch_idempotency_key(
    chatbot_id: int, project_id: int, task: str
) -> str:
    """Return a stable key identifying one launch request.

    Used both for the confirmation marker here and for the Celery
    task's duplicate-launch guard, so a retry of the same request
    recomputes the same key deterministically.
    """
    raw = f"{chatbot_id}:{project_id}:{task.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _pending_confirm_key(idempotency_key: str) -> str:
    return f"hc:pending-confirm:{idempotency_key}"


def mark_pending_confirmation(idempotency_key: str) -> None:
    """Record that the user was just asked to confirm this launch."""
    cache_redis().set(
        _pending_confirm_key(idempotency_key),
        "1",
        ex=_PENDING_CONFIRM_TTL_SECONDS,
    )


def consume_pending_confirmation(idempotency_key: str) -> bool:
    """Return True and clear the marker if a prior ask matches.

    One-time use: a second ``confirmed=true`` call for the same key
    (e.g. a retried tool call) finds no marker and is rejected.
    """
    client = cache_redis()
    key = _pending_confirm_key(idempotency_key)
    pipe = client.pipeline()
    pipe.get(key)
    pipe.delete(key)
    existed, _ = pipe.execute()
    return bool(existed)
