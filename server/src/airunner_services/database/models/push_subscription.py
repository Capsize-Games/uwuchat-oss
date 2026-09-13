"""PushSubscription — Web Push endpoint stored per user."""

from __future__ import annotations

import datetime

from sqlalchemy import Column, DateTime, Integer, Text

from airunner_services.database.base import BaseModel


class PushSubscription(BaseModel):
    """Stores a browser Web Push subscription for a user account."""

    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, nullable=False, index=True)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)
    created_at = Column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )


__all__ = ["PushSubscription"]
