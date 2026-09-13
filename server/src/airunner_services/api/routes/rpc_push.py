"""RPC handlers for Web Push subscription management."""

from __future__ import annotations

import logging
import os
from typing import Any

from airunner_services.api.routes.events import (
    _rpc_error_response,
    _rpc_register,
)

logger = logging.getLogger(__name__)

_VAPID_PUBLIC = os.getenv("VAPID_PUBLIC_KEY", "")


@_rpc_register("GET", "/api/v1/push/vapid-public-key")
async def _rpc_vapid_key(body: dict, **kw: Any) -> dict[str, Any]:
    """Return the VAPID public key needed to create a push subscription."""
    if not _VAPID_PUBLIC:
        return {"status": 503, "body": {"error": "Push not configured"}}
    return {"status": 200, "body": {"public_key": _VAPID_PUBLIC}}


@_rpc_register("POST", "/api/v1/push/subscribe")
async def _rpc_push_subscribe(body: dict, **kw: Any) -> dict[str, Any]:
    """Store a browser push subscription for the current user."""
    try:
        from airunner_services.database.models.push_subscription import (
            PushSubscription,
        )
        endpoint = body.get("endpoint", "")
        p256dh = (body.get("keys") or {}).get("p256dh", "")
        auth = (body.get("keys") or {}).get("auth", "")
        account_id = body.get("account_id", 0)
        if not all([endpoint, p256dh, auth, account_id]):
            return {"status": 400, "body": {"error": "Missing fields"}}
        existing = PushSubscription.objects.filter_by_first(
            endpoint=endpoint
        )
        if existing is None:
            PushSubscription.objects.create(
                account_id=int(account_id),
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
            )
        return {"status": 200, "body": {"subscribed": True}}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="push subscribe error",
        )


@_rpc_register("POST", "/api/v1/push/unsubscribe")
async def _rpc_push_unsubscribe(body: dict, **kw: Any) -> dict[str, Any]:
    """Remove a push subscription by endpoint."""
    try:
        from airunner_services.database.models.push_subscription import (
            PushSubscription,
        )
        endpoint = body.get("endpoint", "")
        if not endpoint:
            return {"status": 400, "body": {"error": "endpoint required"}}
        sub = PushSubscription.objects.filter_by_first(endpoint=endpoint)
        if sub:
            PushSubscription.objects.delete(sub.id)
        return {"status": 200, "body": {"unsubscribed": True}}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="push unsubscribe error",
        )
