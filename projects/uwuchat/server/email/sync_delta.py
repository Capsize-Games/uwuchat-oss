"""JMAP Email/changes delta sync for already-backfilled mailboxes."""

from __future__ import annotations

import datetime
import logging
from typing import Any

from airunner_services.database.models.email_account import EmailAccount
from airunner_services.database.models.email_message import EmailMessage
from airunner_services.database.session import session_scope

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50


def delta_sync_account(
    email_account_id: int,
    provider: Any,
    mailboxes: list,
) -> None:
    """Run JMAP Email/changes delta sync for an account.

    Fetches created/updated emails and marks destroyed ones as deleted.
    Does nothing if the account has no sync_cursor yet (backfill not
    completed).
    """
    with session_scope() as session:
        account = session.query(EmailAccount).get(email_account_id)
        sync_cursor = account.sync_cursor if account else None

    if not sync_cursor:
        return

    changes = _run_async(provider.get_changes(sync_cursor))
    if not changes.new_state:
        return

    fetch_ids = list(set(changes.created + changes.updated))
    if fetch_ids:
        for i in range(0, len(fetch_ids), _BATCH_SIZE):
            batch = fetch_ids[i:i + _BATCH_SIZE]
            emails = _run_async(provider.get_emails(batch))
            _store_updated_emails(email_account_id, emails)

    if changes.destroyed:
        _destroy_emails(email_account_id, changes.destroyed)

    with session_scope() as session:
        account = session.query(EmailAccount).get(email_account_id)
        if account is not None:
            account.sync_cursor = changes.new_state
            account.last_synced_at = datetime.datetime.utcnow()
            session.commit()

    logger.info(
        "Delta sync for account %d: +%d ~%d -%d",
        email_account_id,
        len(changes.created),
        len(changes.updated),
        len(changes.destroyed),
    )


def _store_updated_emails(
    email_account_id: int,
    emails: list,
) -> None:
    """Upsert email metadata from delta fetch.

    Reuses ``_persist_email_metadata``'s skip-if-exists logic from
    ``sync_backfill.py``.  For updated messages, the existing row is
    updated in-place.
    """
    with session_scope() as session:
        for em in emails:
            existing = (
                session.query(EmailMessage)
                .filter(
                    EmailMessage.email_account_id == email_account_id,
                    EmailMessage.provider_message_id == em.provider_id,
                )
                .first()
            )
            if existing is not None:
                existing.subject = em.subject
                existing.from_name = em.from_name
                existing.to_addresses = em.to_addresses
                existing.cc_addresses = em.cc_addresses
                existing.sent_at = _parse_dt(em.sent_at)
            else:
                row = EmailMessage(
                    email_account_id=email_account_id,
                    provider_message_id=em.provider_id,
                    thread_id=em.thread_id,
                    mailbox_role=em.mailbox_role,
                    from_address=em.from_address,
                    from_name=em.from_name,
                    to_addresses=em.to_addresses,
                    cc_addresses=em.cc_addresses,
                    subject=em.subject,
                    sent_at=_parse_dt(em.sent_at),
                    has_attachments=em.has_attachments,
                )
                session.add(row)
        session.commit()


def _destroy_emails(
    email_account_id: int,
    destroyed_ids: list[str],
) -> None:
    """Soft-delete email metadata rows for destroyed JMAP email IDs."""
    with session_scope() as session:
        session.query(EmailMessage).filter(
            EmailMessage.email_account_id == email_account_id,
            EmailMessage.provider_message_id.in_(destroyed_ids),
        ).delete(synchronize_session=False)
        session.commit()


def _run_async(coro):
    """Run an async coroutine in a sync background thread."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _parse_dt(val: str | None) -> datetime.datetime | None:
    """Parse an ISO-8601 datetime string, returning None on failure."""
    if not val:
        return None
    try:
        return datetime.datetime.fromisoformat(
            val.replace("Z", "+00:00"),
        )
    except (ValueError, TypeError):
        return None
