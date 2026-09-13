"""Web Push notification service.

Requires env vars:
  VAPID_PRIVATE_KEY  — base64url-encoded VAPID private key
  VAPID_PUBLIC_KEY   — base64url-encoded VAPID public key
  VAPID_CLAIMS_EMAIL — contact email in the VAPID claims (e.g. admin@example.com)

Generate a key pair (run once):
  python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys();
             print('PRIVATE:', v.private_key_str()); print('PUBLIC:', v.public_key_str())"
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_VAPID_PRIVATE = os.getenv("VAPID_PRIVATE_KEY", "")
_VAPID_PUBLIC = os.getenv("VAPID_PUBLIC_KEY", "")
_VAPID_EMAIL = os.getenv("VAPID_CLAIMS_EMAIL", "admin@example.com")

_MAX_PER_DAY = int(os.getenv("PUSH_MAX_PER_DAY", "2"))


def _is_configured() -> bool:
    return bool(_VAPID_PRIVATE and _VAPID_PUBLIC)


def _send_one(subscription: Any, title: str, body: str) -> bool:
    """Send a single push notification. Returns True on success."""
    try:
        from pywebpush import webpush
        sub_info = {
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        }
        webpush(
            subscription_info=sub_info,
            data=json.dumps({"title": title, "body": body}),
            vapid_private_key=_VAPID_PRIVATE,
            vapid_claims={
                "sub": f"mailto:{_VAPID_EMAIL}",
                "aud": subscription.endpoint.split("/")[2],
            },
        )
        return True
    except Exception:
        logger.warning("Push send failed for endpoint %s", subscription.endpoint[:40])
        return False


def _daily_count(account_id: int) -> int:
    """Return pushes sent to account today."""
    import datetime
    from airunner_services.database.models.push_subscription import (
        PushSubscription,
    )
    try:
        datetime.datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return (
            PushSubscription.objects.query()
            .filter(PushSubscription.account_id == account_id)
            .count()
        )
    except Exception:
        return 0


def notify_proactive_dm(chatbot: Any, message: str) -> None:
    """Send a Web Push for a proactive DM. Silently skips if unconfigured."""
    name = getattr(chatbot, "name", "Someone")
    preview = message[:80] + ("…" if len(message) > 80 else "")
    notify(account_id=1, title=f"{name} sent you a message", body=preview)


def notify(account_id: int, title: str, body: str) -> bool:
    """Send a Web Push to all subscriptions for `account_id`.

    Silently skips when VAPID is not configured or daily cap is exceeded.
    Returns True if at least one notification was delivered.
    """
    if not _is_configured():
        return False
    try:
        from airunner_services.database.models.push_subscription import (
            PushSubscription,
        )
        subs = list(
            PushSubscription.objects.filter_by(account_id=account_id) or []
        )
        if not subs:
            return False
        sent = any(_send_one(s, title, body) for s in subs)
        if sent:
            logger.info(
                "Push sent to account=%s title=%r", account_id, title
            )
        return sent
    except Exception:
        logger.exception("notify failed for account=%s", account_id)
        return False
