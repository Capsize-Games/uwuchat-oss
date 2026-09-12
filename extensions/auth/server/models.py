"""Auth extension — SQLAlchemy models.

The ``Account`` model lives in the **public** schema (shared across all
tenants) and stores authentication credentials.  Every other model in
the system lives inside tenant-scoped schemas.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)

from airunner_services.database.base import BaseModel

from airunner_services.contract_enums import ModelService


class Account(BaseModel):
    """Authentication account — one row per registered user.

    This model lives outside tenant schemas (``__public_schema__ = True``)
    so it can be queried before tenant context is established — e.g.
    during login.
    """

    __tablename__ = "accounts"
    __public_schema__ = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)  # Nullable for OAuth-only accounts
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)
    is_suspended = Column(Boolean, default=False, nullable=False)
    is_banned = Column(Boolean, nullable=True)
    ban_reason = Column(String, nullable=True)
    tenant_schema = Column(String, unique=True, nullable=False)
    created_at = Column(
        DateTime,
        # Callable default — evaluated per-insert.  A bare
        # ``datetime.now(...)`` value would be frozen at import time and
        # stamp every new row with the process start time.
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    last_login = Column(DateTime, nullable=True)

    # OAuth fields
    google_id = Column(String, nullable=True, unique=True)
    steam_id = Column(String, nullable=True, unique=True)
    twitch_id = Column(String, nullable=True, unique=True)
    # "local" | "google" | "steam" | "twitch"
    auth_provider = Column(
        String, nullable=False, default=ModelService.LOCAL.value
    )

    # Bumped to revoke all outstanding refresh tokens (logout-everywhere).
    token_version = Column(Integer, nullable=False, default=0)

    # Terms of Service agreement fields — recorded at registration.
    tos_agreed = Column(Boolean, nullable=False, default=False)
    age_confirmed = Column(Boolean, nullable=False, default=False)
    entertainment_confirmed = Column(Boolean, nullable=False, default=False)
    tos_agreed_at = Column(DateTime, nullable=True)
    tos_agreed_ip = Column(String(64), nullable=True)

    # Sensitive-data consent — required only for Japan (JP), India (IN),
    # and Canada (CA), which have consent-based privacy regimes without
    # GDPR's default-prohibition posture.  Mirrors the tos_agreed*
    # naming shape.
    sensitive_data_consent_agreed = Column(
        Boolean, nullable=False, default=False
    )
    sensitive_data_consent_at = Column(DateTime, nullable=True)
    sensitive_data_consent_ip = Column(String(64), nullable=True)

    updated_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    deleted = Column(Boolean, nullable=False, default=False)

    # ── UwUChat code credits (real-dollar prepaid balance) ─────────────
    # Admin-only for now: manual top-up via the code-credits API, debited
    # per headlesscode session. Lives on the public-schema accounts table
    # (not a tenant schema). Numeric, never Float — sub-cent LLM costs
    # must not drift across many small debits.
    code_credits_usd = Column(Numeric(10, 4), nullable=False, default=0)

    # ── User-controlled key envelope (per-user encryption at rest) ────
    # The DEK is wrapped with a KEK derived from the user's password.
    # None for OAuth-only accounts (no password → no envelope) and
    # legacy accounts that haven't logged in since the migration.
    wrapped_dek = Column(Text, nullable=True)
    dek_kdf_salt = Column(String(64), nullable=True)
    dek_kdf_params = Column(JSON, nullable=True)
    dek_version = Column(Integer, nullable=False, default=1)


# Re-export so the extension loader discovers these models
# via dir() when it scans this module.
from extensions.auth.server.password_reset_token import PasswordResetToken
from extensions.auth.server.waitlist_entry import WaitlistEntry

__all__ = [
    "Account",
    "PasswordResetToken",
    "WaitlistEntry",
]
