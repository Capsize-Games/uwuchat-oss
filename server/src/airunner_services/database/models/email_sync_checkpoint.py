"""EmailSyncCheckpoint — resumable backfill progress per mailbox."""

from __future__ import annotations

import datetime

from sqlalchemy import Column, DateTime, Integer, String

from airunner_services.database.base import BaseModel


class EmailSyncCheckpoint(BaseModel):
    """Tracks backfill progress for one mailbox of one email account.

    A crashed or restarted job resumes from the stored cursor position
    rather than re-fetching everything from the beginning.
    """

    __tablename__ = "email_sync_checkpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email_account_id = Column(Integer, nullable=False, index=True)
    mailbox_id = Column(String(255), nullable=False)
    mailbox_role = Column(String(32), nullable=False)
    last_position = Column(Integer, nullable=True)
    last_email_id = Column(String(255), nullable=True)
    emails_processed = Column(Integer, nullable=False, default=0)
    status = Column(
        String(16), nullable=False, default="pending",
    )
    updated_at = Column(
        DateTime,
        default=datetime.datetime.now,
        onupdate=datetime.datetime.now,
    )


__all__ = ["EmailSyncCheckpoint"]
