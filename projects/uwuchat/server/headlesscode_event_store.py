"""Cross-process headlesscode event outbox (Redis DB 3).

The Celery worker that polls running headlesscode sessions runs in a
separate process from the API server, so its discoveries cannot be
pushed over the in-process ``WsEventBus`` — a broadcast made there
would only reach that worker's own (subscriber-less) event-bus
singleton and never the browser (see ``email/sync_progress_events.py``
for the same constraint and its Redis workaround).

This store is the headlesscode equivalent: one Redis list acting as an
outbox. The worker appends one JSON payload per new session event
(plus session status transitions); the API server's in-process
forwarder (``headlesscode_ws_forwarder``) drains the list and
republishes each payload through the ``/api/v1/events`` WebSocket
channel as the account-scoped ``headlesscode_session`` event type.
"""

from __future__ import annotations

import json
from typing import Any

from airunner_services.tasks.redis_client import cache_redis

_OUTBOX_KEY = "hc:event:outbox"
# Refreshed on every append; lets the list self-clean when a session
# goes quiet for a long stretch and nothing is left to forward.
_OUTBOX_TTL_SECONDS = 300


def headlesscode_events_append(payload: dict[str, Any]) -> None:
    """Append one forwardable event payload to the outbox."""
    r = cache_redis()
    r.rpush(_OUTBOX_KEY, json.dumps(payload, default=str))
    r.expire(_OUTBOX_KEY, _OUTBOX_TTL_SECONDS)


def headlesscode_events_drain(limit: int = 200) -> list[dict[str, Any]]:
    """Pop and return up to *limit* queued payloads, oldest first.

    Safe under a single consumer (the one API server process): each
    ``LPOP`` is atomic, and a payload appended while draining is left
    for the next pass. Malformed entries are dropped.
    """
    r = cache_redis()
    drained: list[dict[str, Any]] = []
    for _ in range(limit):
        raw = r.lpop(_OUTBOX_KEY)
        if raw is None:
            break
        try:
            drained.append(json.loads(raw))
        except ValueError:
            continue
    return drained


__all__ = ["headlesscode_events_append", "headlesscode_events_drain"]
