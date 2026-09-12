"""In-process forwarder: uwu_creation Redis outbox → WebSocket push.

The Celery task that generates a random chatbot writes terminal status
transitions to a Redis outbox (``uwu_creation_event_store``) because it
runs in a different process from the API server — a direct
``WsEventBus`` broadcast from the worker would never reach browser
connections held by the API server process (see
``headlesscode_ws_forwarder.py`` for the same pattern).

This module runs *inside* the API server process: it periodically
drains the outbox and republishes each payload through the unified
``/api/v1/events`` channel (``WsEventBus``) as the account-scoped
``uwu_creation`` event type, scoped by ``account_id`` so a subscriber
only ever receives its own creations' events.
"""

from __future__ import annotations

import asyncio
import logging

from airunner_services.api.routes.events_bus import WsEventBus
from airunner_services.api.routes.events_rpc import EVENT_UWU_CREATION

from projects.uwuchat.server.uwu_creation_event_store import (
    uwu_creation_events_drain,
)

logger = logging.getLogger(__name__)

# How often to poll the outbox. Generation completes in seconds; 0.5s
# keeps the loop cheap while staying responsive.
_DRAIN_INTERVAL_SECONDS = 0.5
# Max payloads per drain pass — bounds the work done in one iteration
# when the API server comes back up after a long outage.
_DRAIN_BATCH = 200


async def _forward_loop() -> None:
    """Drain the outbox and republish every payload over the WS bus."""
    loop = asyncio.get_running_loop()
    bus = WsEventBus()
    while True:
        try:
            payloads = await loop.run_in_executor(
                None, uwu_creation_events_drain, _DRAIN_BATCH,
            )
            for payload in payloads:
                account_id = payload.get("account_id")
                if account_id is None:
                    # Every payload must carry its owner; without one a
                    # broadcast would be unscoped (a cross-account
                    # leak). Drop it rather than risk that.
                    continue
                bus.broadcast(
                    EVENT_UWU_CREATION,
                    payload,
                    account_id=account_id,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug(
                "uwu_creation forward iteration failed", exc_info=True,
            )
        await asyncio.sleep(_DRAIN_INTERVAL_SECONDS)


def start_uwu_creation_ws_forwarder() -> asyncio.Task:
    """Launch the forward loop as a background task."""
    return asyncio.create_task(_forward_loop())


__all__ = ["start_uwu_creation_ws_forwarder"]
