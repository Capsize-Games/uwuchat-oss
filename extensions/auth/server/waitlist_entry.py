"""Waitlist entry model — public schema, gated registration queue.

Each row is one person who joined the waitlist. When the owner
releases a batch, a hashed invite token is stored — the raw token
is never persisted.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from airunner_services.database.base import BaseModel


class WaitlistEntry(BaseModel):
    """One row per waitlist signup.

    Stores email and (when invited) a hash of the one-time invite token.
    The raw token is only held in the invitation email and the admin
    release response — never written to disk.
    """

    __tablename__ = "waitlist_entries"
    __public_schema__ = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    ip_address = Column(String(64), nullable=True)
    token_hash = Column(String, nullable=True, unique=True)
    token_expires_at = Column(DateTime, nullable=True)
    invited_at = Column(DateTime, nullable=True)
    converted_account_id = Column(
        Integer, ForeignKey("accounts.id"), nullable=True,
    )
    converted_at = Column(DateTime, nullable=True)


__all__ = ["WaitlistEntry"]
