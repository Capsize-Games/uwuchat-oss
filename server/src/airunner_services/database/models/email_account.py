"""EmailAccount — one linked Fastmail (or future provider) account."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String

from airunner_services.database.base import BaseModel
from airunner_services.utils.crypto import UserEncryptedText


class EmailAccount(BaseModel):
    """One email account linked to a user.

    Stores the API token encrypted via the per-user DEK pattern.
    ``sync_cursor`` holds the JMAP state token for incremental
    ``Email/changes`` sync after the initial backfill completes.

    ``indexing_status`` tracks whether background body-chunk indexing
    has completed (``"complete"``), was skipped due to a missing DEK
    (``"pending"``), or is unknown (``None`` — accounts synced before
    this field was added).

    ``indexing_recovery_checked_at`` is a debounce timestamp for the
    login-recovery hook (``recover_pending_email_indexing``).  The
    hook skips an account if this timestamp is within the cooldown
    window (30 minutes), preventing redundant Celery enqueues on
    frequent logins.
    """

    __tablename__ = "email_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    provider = Column(String(32), nullable=False, default="fastmail")
    email_address = Column(String(255), nullable=False)
    credential_ciphertext = Column(UserEncryptedText, nullable=False)
    status = Column(String(16), nullable=False, default="connected")
    error_message = Column(String(512), nullable=True)
    sync_cursor = Column(String(255), nullable=True)
    backfill_completed_at = Column(DateTime, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    indexing_status = Column(String(16), nullable=True)
    last_indexed_at = Column(DateTime, nullable=True)
    indexing_recovery_checked_at = Column(DateTime, nullable=True)


__all__ = ["EmailAccount"]
