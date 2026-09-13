"""Password reset token model (public schema).

Each row represents one requested password-reset link. The raw token
is never stored — only its SHA-256 hash, so a database read cannot
produce a usable reset link.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from airunner_services.database.base import BaseModel


class PasswordResetToken(BaseModel):
    """One row per password-reset request.

    Stores a hash of the token (not the token itself). Expires after
    one hour. Marked used on redemption to prevent replay.
    """

    __tablename__ = "password_reset_tokens"
    __public_schema__ = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )


__all__ = ["PasswordResetToken"]
