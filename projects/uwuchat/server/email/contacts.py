"""Contact extraction from email headers — pure aggregation (Phase 2).

No LLM involved.  Upserts on the (user_id, email_address) unique
constraint.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from airunner_services.database.models.email_contact import EmailContact
from airunner_services.database.models.email_message import EmailMessage
from airunner_services.database.session import session_scope

from .sync_progress_events import emit_progress

logger = logging.getLogger(__name__)


def extract_contacts(
    email_account_id: int,
    user_id: int,
    messages: list[Any],
) -> None:
    """Aggregate From/To/Cc headers into email_contacts.

    *messages* are provider-level EmailMessage dataclass instances,
    not ORM objects. One bulk upsert per call (counts pre-aggregated
    in Python) instead of one SELECT+write per recipient.
    """
    if not messages:
        return
    touched = _upsert_contacts(user_id, messages)
    emit_progress(
        email_account_id, "Analyzing contacts",
        len(messages), len(messages), unit="messages",
    )
    _resolve_entities_for_contacts(user_id, touched)


def _aggregate_recipients(messages: list[Any]) -> dict[str, dict]:
    """Aggregate per-address occurrence counts across *messages*."""
    agg: dict[str, dict] = {}
    for msg in messages:
        from_addr = (getattr(msg, "from_address", "") or "").strip().lower()
        recipients: list[tuple[str, str]] = []
        if from_addr:
            recipients.append((from_addr, getattr(msg, "from_name", "") or ""))
        for addr in (
            getattr(msg, "to_addresses", None) or []
        ) + (
            getattr(msg, "cc_addresses", None) or []
        ):
            email = (addr.get("address") or "").strip().lower()
            if email:
                recipients.append((email, addr.get("name", "")))

        for email, name in recipients:
            entry = agg.setdefault(email, {"name": "", "from": 0, "to": 0})
            entry["name"] = entry["name"] or name
            if email == from_addr:
                entry["from"] += 1
            else:
                entry["to"] += 1
    return agg


def _upsert_contacts(
    user_id: int,
    messages: list[Any],
) -> list[tuple[str, str, int]]:
    """Bulk-upsert email_contacts; returns touched (email, name, id)."""
    aggregated = _aggregate_recipients(messages)
    if not aggregated:
        return []

    now = datetime.datetime.utcnow()
    rows = [
        {
            "user_id": user_id,
            "email_address": email,
            "display_name": info["name"] or None,
            "first_seen_at": now,
            "last_seen_at": now,
            "message_count_from": info["from"],
            "message_count_to": info["to"],
        }
        for email, info in aggregated.items()
    ]

    with session_scope() as session:
        stmt = pg_insert(EmailContact).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "email_address"],
            set_={
                "last_seen_at": stmt.excluded.last_seen_at,
                "message_count_from": (
                    EmailContact.message_count_from
                    + stmt.excluded.message_count_from
                ),
                "message_count_to": (
                    EmailContact.message_count_to
                    + stmt.excluded.message_count_to
                ),
                "display_name": func.coalesce(
                    EmailContact.display_name, stmt.excluded.display_name,
                ),
            },
        ).returning(
            EmailContact.email_address,
            EmailContact.display_name,
            EmailContact.id,
        )
        result = session.execute(stmt).all()
        session.commit()
        return [(r[0], r[1], r[2]) for r in result]


def compute_response_times(
    user_id: int,
    messages: list[Any],
) -> None:
    """Compute avg_response_time_seconds heuristics for contacts.

    Compares timestamp of a sent message with the timestamp of the
    most recent received message in the same thread from that contact.
    """
    with session_scope() as session:
        contacts = (
            session.query(EmailContact)
            .filter(
                EmailContact.user_id == user_id,
                EmailContact.message_count_to > 0,
            )
            .all()
        )
        for contact in contacts:
            contact.avg_response_time_seconds = _estimate_response(
                session, user_id, contact,
            )
        session.commit()


def _estimate_response(session, user_id: int, contact) -> Optional[int]:
    """Heuristic: median time between receive→send in same thread.

    Note: ``EmailMessage.from_address`` is encrypted at rest via
    ``UserEncryptedText``, so SQL-level comparisons against plaintext
    never match.  This function fetches sent messages and then matches
    the contact's address in Python after decryption, which is safe
    here because it operates on a small per-contact lookup rather than
    a bulk scan.
    """
    from airunner_services.database.models.email_account import (
        EmailAccount,
    )

    # Build a proper column-attribute subquery instead of raw string
    # references to "email_accounts.c.id" / "email_accounts.c.user_id".
    account_id_subq = (
        session.query(EmailAccount.id)
        .filter(EmailAccount.user_id == user_id)
        .subquery()
    )

    sent_messages = (
        session.query(EmailMessage)
        .filter(
            EmailMessage.email_account_id.in_(account_id_subq),
            EmailMessage.mailbox_role == "sent",
        )
        .all()
    )
    if not sent_messages:
        return None
    deltas: list[int] = []
    for sm in sent_messages:
        # from_address is encrypted ciphertext — compare in Python
        # after SQLAlchemy's UserEncryptedText decrypts it on read.
        last_from = (
            session.query(EmailMessage)
            .filter(
                EmailMessage.thread_id == sm.thread_id,
                EmailMessage.mailbox_role != "sent",
            )
            .order_by(EmailMessage.sent_at.desc())
            .first()
        )
        if (
            last_from
            and last_from.sent_at
            and sm.sent_at
            and _decrypted_addr_matches(last_from, contact.email_address)
        ):
            delta = sm.sent_at - last_from.sent_at
            deltas.append(int(delta.total_seconds()))
    if not deltas:
        return None
    deltas.sort()
    return deltas[len(deltas) // 2]


def _decrypted_addr_matches(
    message: EmailMessage, plaintext_addr: str,
) -> bool:
    """Return True if the decrypted ``from_address`` matches *plaintext_addr*.

    ``EmailMessage.from_address`` is a ``UserEncryptedText`` column —
    SQLAlchemy decrypts it on attribute access.  We compare in Python
    because the ciphertext never equals the plaintext string.
    """
    decrypted = getattr(message, "from_address", None)
    if decrypted is None:
        return False
    return decrypted.strip().lower() == (plaintext_addr or "").strip().lower()


def _resolve_entities_for_contacts(
    user_id: int,
    contact_rows: list[tuple[str, str, int]],
) -> None:
    """Create/update Entity rows for the given (already-touched) rows.

    Takes rows the caller just touched via ``RETURNING`` instead of
    re-scanning every contact the user has ever had on every chunk.
    Owner's address gets ``source_type="account_owner"``, others get
    ``"email_contact"``. Reads happen first in one session; resolution
    (which opens its own sessions) runs after — ``session_scope()``
    isn't reentrant, so it must not run while this session is open.
    """
    if not contact_rows:
        return

    from airunner_services.database.models.chatbot import Chatbot
    from airunner_services.database.models.email_account import (
        EmailAccount,
    )
    from airunner_services.entity_resolver import resolve_entity

    with session_scope() as session:
        bot = (
            session.query(Chatbot)
            .filter(Chatbot.is_system_bot.is_(True))
            .first()
        )
        if bot is None:
            return
        system_bot_id = bot.id

        user_emails: set[str] = set()
        for acct in (
            session.query(EmailAccount)
            .filter(
                EmailAccount.user_id == user_id,
                EmailAccount.deleted == False,
            )
            .all()
        ):
            addr = (
                getattr(acct, "email_address", "") or ""
            ).strip().lower()
            if addr:
                user_emails.add(addr)

    for raw_email, display_name, contact_id in contact_rows:
        email = (raw_email or "").strip().lower()
        if not email:
            continue
        source_type = (
            "account_owner" if email in user_emails else "email_contact"
        )
        resolve_entity(
            name=display_name or email,
            chatbot_id=system_bot_id,
            entity_type="person",
            source_type=source_type,
            source_ref_table="email_contacts",
            source_ref_id=contact_id,
        )
