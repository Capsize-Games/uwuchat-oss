"""Concurrent email-body fetching for the Phase 2-4 pipeline.

Split out of ``sync_pipeline.py`` to stay under the project's
line-count limit. JMAP sub-batches fetch concurrently on one event
loop instead of sequentially on a fresh loop each — the latter meant
the next batch's HTTP request didn't even start until the previous
one fully returned.

Global concurrency gate
-----------------------
Fastmail's published JMAP session limits include:
- ``maxConcurrentRequests: 10``
- ``maxCallsInRequest: 50``
- ``maxObjectsInSet: 4096``

This module guards the *total* number of in-flight JMAP HTTP requests
across the entire application with a ``threading.Semaphore`` — not an
``asyncio.Semaphore`` — because each worker thread runs its own
independent event loop via ``run_async``. The semaphore is acquired
immediately before each ``provider.get_emails(...)`` call inside
``_gather_batches``, ensuring the bound applies globally regardless
of how many outer worker threads or inner sub-batches exist.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

# Fastmail's published JMAP session capability: maxConcurrentRequests: 10.
# This is a global ceiling enforced by a threading.Semaphore (see module
# docstring). Acquired per provider.get_emails() call inside _gather_batches.
_MAX_CONCURRENT_JMAP_REQUESTS = 10

# Fastmail's maxCallsInRequest: 50. Each get_emails call is one JMAP
# method call. maxObjectsInSet: 4096.  250 IDs per request stays safely
# under both limits while reducing total round-trips vs the previous 50.
_BATCH_SIZE = 250

# Thread-safe semaphore — not an asyncio.Semaphore — because each worker
# thread runs its own event loop and asyncio.Semaphores don't coordinate
# across threads. See module docstring for the full rationale.
_jmap_concurrency_semaphore = threading.Semaphore(
    _MAX_CONCURRENT_JMAP_REQUESTS,
)


def fetch_email_bodies(provider: Any, ids: set[str]) -> list[Any]:
    """Fetch email bodies for one chunk, JMAP sub-batches concurrently."""
    fetch_list = list(ids)
    batches = [
        fetch_list[i:i + _BATCH_SIZE]
        for i in range(0, len(fetch_list), _BATCH_SIZE)
    ]
    if not batches:
        return []

    results = run_async(_gather_batches(provider, batches))
    all_emails: list[Any] = []
    for batch_result in results:
        all_emails.extend(batch_result)
    return all_emails


async def _gather_batches(provider: Any, batches: list[list[str]]):
    """Fetch every batch concurrently on one event loop.

    Acquires the global ``threading.Semaphore`` before each
    ``provider.get_emails`` call to bound the total number of
    in-flight JMAP HTTP requests to ``_MAX_CONCURRENT_JMAP_REQUESTS``
    regardless of how many outer worker threads or inner sub-batches
    exist.  ``asyncio.to_thread`` is used to acquire the
    blocking ``threading.Semaphore`` without blocking the event loop.
    """
    async def _fetch_with_semaphore(batch):
        await asyncio.to_thread(_jmap_concurrency_semaphore.acquire)
        try:
            return await provider.get_emails(batch)
        finally:
            _jmap_concurrency_semaphore.release()

    return await asyncio.gather(*(
        _fetch_with_semaphore(batch) for batch in batches
    ))


def run_async(coro):
    """Run an async coroutine in a sync background thread."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


__all__ = ["fetch_email_bodies", "run_async"]
