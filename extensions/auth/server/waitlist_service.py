"""Waitlist business logic — importable without FastAPI.

Uses the same small service-module style as the other auth helpers:
plain functions,
public_session_scope(), no classes.
"""

from __future__ import annotations

import datetime
import hashlib
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from airunner_services.database.session import public_session_scope
from extensions.auth.server.waitlist_entry import WaitlistEntry

_TOKEN_BYTES = 32
_TOKEN_EXPIRY_DAYS = 7


def join_waitlist(email: str, ip_address: Optional[str]) -> None:
    """Idempotent insert — no-op if the email is already on the list.

    Always succeeds so the caller cannot probe whether an email is
    already registered (the same success response is returned either
    way).
    """
    clean = email.strip().lower()
    with public_session_scope() as session:
        existing = (
            session.query(WaitlistEntry)
            .filter(WaitlistEntry.email == clean)
            .first()
        )
        if existing is not None:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        entry = WaitlistEntry(
            email=clean,
            created_at=now,
            ip_address=ip_address,
        )
        session.add(entry)


def issue_invites(count: int) -> list[WaitlistEntry]:
    """Select the oldest *count* uninvited rows and assign tokens.

    Returns the (still-attached) rows so the caller can send emails
    with the raw tokens. The raw token is returned in a transient
    attribute and must never be persisted.
    """
    with public_session_scope() as session:
        rows = (
            session.query(WaitlistEntry)
            .filter(WaitlistEntry.token_hash.is_(None))
            .order_by(WaitlistEntry.created_at.asc())
            .limit(count)
            .all()
        )
        now = datetime.datetime.now(datetime.timezone.utc)
        result: list[WaitlistEntry] = []
        for row in rows:
            raw = secrets.token_urlsafe(_TOKEN_BYTES)
            row.token_hash = hashlib.sha256(
                raw.encode()
            ).hexdigest()
            row.token_expires_at = now + datetime.timedelta(
                days=_TOKEN_EXPIRY_DAYS,
            )
            row.invited_at = now
            session.add(row)
            # Attach raw token as a transient attribute so the caller
            # can read it after session.flush() / expunge.
            row._raw_token = raw  # type: ignore[attr-defined]
            result.append(row)
        session.flush()
        for row in result:
            session.expunge(row)
        return result


def redeem_invite_token(
    raw_token: str,
    *,
    _session: Optional[Session] = None,
) -> Optional[WaitlistEntry]:
    """Validate *raw_token* and return the WaitlistEntry if valid.

    Returns None for invalid, expired, or already-converted tokens.

    Uses ``SELECT ... FOR UPDATE`` row locking so two concurrent
    registrations with the same token cannot both succeed — the
    second caller blocks until the first commits, then sees
    ``converted_account_id IS NOT NULL`` and returns None.

    When *_session* is provided the lookup runs inside the caller's
    transaction so the row can be marked consumed atomically with
    account creation.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    def _redeem(session: Session) -> Optional[WaitlistEntry]:
        now = datetime.datetime.now(datetime.timezone.utc)
        entry = (
            session.query(WaitlistEntry)
            .filter(WaitlistEntry.token_hash == token_hash)
            .with_for_update()
            .first()
        )
        if entry is None:
            return None
        if entry.converted_account_id is not None:
            return None
        if (
            entry.token_expires_at is not None
            and entry.token_expires_at < now
        ):
            return None
        return entry

    if _session is not None:
        return _redeem(_session)
    with public_session_scope() as session:
        return _redeem(session)
