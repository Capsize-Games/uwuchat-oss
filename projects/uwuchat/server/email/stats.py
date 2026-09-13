"""Compute EmailStats — cheap aggregate rollups shown on the profile
panel after a sync completes.

``EmailStats`` (framework model) was defined for exactly this but had
no writer — this is that writer, called once per successful sync from
``_sync_callback``.
"""

from __future__ import annotations

import datetime

from sqlalchemy import func

from airunner_services.database.models.email_contact import EmailContact
from airunner_services.database.models.email_message import EmailMessage
from airunner_services.database.models.email_stats import EmailStats
from airunner_services.database.session import session_scope

_TOP_CONTACTS_LIMIT = 5
_SENT_ROLES = ("sent",)


def compute_email_stats(email_account_id: int, user_id: int) -> None:
    """Recompute and upsert the ``all_time`` EmailStats row."""
    with session_scope() as session:
        total_messages = (
            session.query(func.count(EmailMessage.id))
            .filter(
                EmailMessage.email_account_id == email_account_id,
                EmailMessage.deleted == False,
            )
            .scalar()
        ) or 0

        sent_count = (
            session.query(func.count(EmailMessage.id))
            .filter(
                EmailMessage.email_account_id == email_account_id,
                EmailMessage.mailbox_role.in_(_SENT_ROLES),
                EmailMessage.deleted == False,
            )
            .scalar()
        ) or 0

        top_contacts = _top_contacts(session, user_id)

        row = (
            session.query(EmailStats)
            .filter(
                EmailStats.email_account_id == email_account_id,
                EmailStats.period == "all_time",
            )
            .first()
        )
        if row is None:
            row = EmailStats(
                email_account_id=email_account_id,
                period="all_time",
            )
            session.add(row)

        row.total_messages = total_messages
        row.sent_count = sent_count
        row.received_count = max(total_messages - sent_count, 0)
        row.top_contacts = top_contacts
        row.computed_at = datetime.datetime.utcnow()
        session.commit()


def _top_contacts(session, user_id: int) -> list[dict]:
    """Return the top contacts by total message count."""
    contacts = (
        session.query(EmailContact)
        .filter(EmailContact.user_id == user_id)
        .order_by(
            (
                EmailContact.message_count_from
                + EmailContact.message_count_to
            ).desc(),
        )
        .limit(_TOP_CONTACTS_LIMIT)
        .all()
    )
    return [
        {
            "email_address": c.email_address,
            "display_name": c.display_name,
            "message_count": (
                c.message_count_from + c.message_count_to
            ),
        }
        for c in contacts
    ]


__all__ = ["compute_email_stats"]
