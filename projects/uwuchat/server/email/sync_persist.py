"""Bulk-persist fetched email metadata to email_messages.

Split out of ``sync_backfill.py`` to stay under the project's
line-count limit.
"""

from __future__ import annotations

import datetime

from airunner_services.database.models.email_message import EmailMessage
from airunner_services.database.session import session_scope


def persist_email_metadata(
    email_account_id: int,
    emails: list,
    mailbox_role: str,
) -> None:
    """Write email metadata rows (no body) to the database.

    One bulk existence-check plus one bulk insert instead of a
    SELECT-then-INSERT round trip per message (no unique constraint
    exists on (email_account_id, provider_message_id) to use
    ``ON CONFLICT`` — this stays a plain check-then-insert, just
    batched instead of per-row).
    """
    if not emails:
        return
    with session_scope() as session:
        provider_ids = [em.provider_id for em in emails]
        existing_ids = {
            r[0] for r in session.query(EmailMessage.provider_message_id)
            .filter(
                EmailMessage.email_account_id == email_account_id,
                EmailMessage.provider_message_id.in_(provider_ids),
            ).all()
        }
        new_rows = [
            {
                "email_account_id": email_account_id,
                "provider_message_id": em.provider_id,
                "thread_id": em.thread_id,
                "mailbox_role": mailbox_role,
                "from_address": em.from_address,
                "from_name": em.from_name,
                "to_addresses": em.to_addresses,
                "cc_addresses": em.cc_addresses,
                "subject": em.subject,
                "sent_at": _parse_dt(em.sent_at),
                "has_attachments": em.has_attachments,
            }
            for em in emails
            if em.provider_id not in existing_ids
        ]
        if new_rows:
            session.bulk_insert_mappings(EmailMessage, new_rows)
        session.commit()


def _parse_dt(val: str | None) -> datetime.datetime | None:
    """Parse an ISO-8601 datetime string, returning None on failure."""
    if not val:
        return None
    try:
        return datetime.datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


__all__ = ["persist_email_metadata"]
