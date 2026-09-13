"""EmailStats — cheap aggregate rollups for dashboards and context."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from airunner_services.database.base import BaseModel


class EmailStats(BaseModel):
    """Non-sensitive aggregate counts for one email account.

    Refreshed on each sync cycle.  The ``top_contacts`` JSON array is a
    small denormalized snapshot derived from ``email_contacts``.
    """

    __tablename__ = "email_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email_account_id = Column(Integer, nullable=False, index=True)
    period = Column(
        String(16), nullable=False, default="all_time",
    )
    total_messages = Column(Integer, nullable=False, default=0)
    sent_count = Column(Integer, nullable=False, default=0)
    received_count = Column(Integer, nullable=False, default=0)
    top_contacts = Column(JSONB, nullable=True)
    computed_at = Column(DateTime, nullable=False)


__all__ = ["EmailStats"]
