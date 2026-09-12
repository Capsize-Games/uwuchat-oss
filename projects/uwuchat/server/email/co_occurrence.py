"""Non-LLM co-occurrence builder for entity_relationships.

Pure aggregation over ``email_messages``' to/cc addresses — no model
call, no API cost, scales with message volume the same way
``extract_contacts()`` does.

For every email with multiple participants (including the account
owner), every pair gets their ``entity_relationships`` edge
incremented.  All entities created or looked up here use
``chatbot_id = <system bot id>`` (hard rule from the entity plan).
"""

from __future__ import annotations

import datetime
import itertools
import logging

from airunner_services.database.models.chatbot import Chatbot
from airunner_services.database.models.email_account import EmailAccount
from airunner_services.database.models.email_message import EmailMessage
from airunner_services.database.models.entity_relationship import (
    EntityRelationship,
)
from airunner_services.database.session import session_scope
from airunner_services.entity_resolver import resolve_entity

from .sync_progress_events import emit_progress

logger = logging.getLogger(__name__)


def build_co_occurrence_graph(
    email_account_id: int,
) -> int:
    """Aggregate to/cc co-occurrences into entity_relationships.

    For every email message with multiple participants, resolve each
    person to an Entity (creating one if needed, scoped to the system
    bot), then increment the entity_relationships edge for every pair.

    The account owner gets their own Entity row (source_type=
    "account_owner"), included in edges like any other participant.

    Returns the number of edges touched.
    """
    with session_scope() as session:
        bot = (
            session.query(Chatbot)
            .filter(Chatbot.is_system_bot.is_(True))
            .first()
        )
        if bot is None:
            return 0
        system_bot_id = bot.id

        # Get the user's own email addresses for account-owner
        # resolution.
        account = session.query(EmailAccount).get(email_account_id)
        if account is None or account.deleted:
            return 0
        owner_email = (
            getattr(account, "email_address", "") or ""
        ).strip().lower()
        edges_touched = 0

    # Process in chunks to avoid loading all messages into memory.
    # No offset: each chunk's messages get marked processed and drop
    # out of the "unprocessed" filter, so the next unfiltered chunk
    # naturally picks up where the last one left off. An offset here
    # would skip messages, since the filtered set shrinks by exactly
    # the offset's own step size on every iteration.
    chunk_size = 100
    total = _count_unprocessed(email_account_id)
    done = 0
    while True:
        chunk = _load_message_chunk(email_account_id, chunk_size)
        if not chunk:
            break

        # Entity resolution happens *outside* any open session_scope —
        # resolve_entity() opens its own, and session_scope() is not
        # safely reentrant (nested calls share one thread-local
        # session; the inner call's exit tears it down for the outer
        # one too, detaching whatever it still had loaded).
        participants_by_msg = {
            msg_id: _resolve_participants(
                to_addrs, cc_addrs, from_addr, from_name,
                owner_email, system_bot_id,
            )
            for msg_id, to_addrs, cc_addrs, from_addr, from_name
            in chunk
        }

        with session_scope() as session:
            processed_ids = [msg_id for msg_id, *_ in chunk]
            for participants in participants_by_msg.values():
                edges_touched += _write_edges(session, participants)
            _batch_mark_processed(session, processed_ids)
            session.commit()

        done += len(chunk)
        emit_progress(
            email_account_id, "Building relationship graph",
            done, total, unit="messages",
        )

    return edges_touched


def _count_unprocessed(email_account_id: int) -> int:
    """Return the count of messages still needing co-occurrence work.

    Filtered the same way as ``_load_message_chunk`` — otherwise the
    denominator would include automated messages that never get
    marked processed (they're never selected into a chunk), and the
    progress bar would get stuck short of 100%.
    """
    with session_scope() as session:
        return (
            session.query(EmailMessage)
            .filter(
                EmailMessage.email_account_id == email_account_id,
                EmailMessage.co_occurrence_processed_at.is_(None),
                EmailMessage.is_automated == False,
                EmailMessage.deleted == False,
            )
            .count()
        )


def _load_message_chunk(
    email_account_id: int,
    limit: int,
) -> list[tuple]:
    """Return plain-value tuples for one chunk of unprocessed messages.

    Automated messages (newsletters, notifications) are skipped —
    a mass CC list on a company announcement isn't a real
    relationship between the people on it, and including them was
    part of what made the network graph an unreadable wall of noise.
    """
    with session_scope() as session:
        messages = (
            session.query(EmailMessage)
            .filter(
                EmailMessage.email_account_id == email_account_id,
                EmailMessage.co_occurrence_processed_at.is_(None),
                EmailMessage.is_automated == False,
                EmailMessage.deleted == False,
            )
            .order_by(EmailMessage.id)
            .limit(limit)
            .all()
        )
        return [
            (
                msg.id, msg.to_addresses, msg.cc_addresses,
                msg.from_address, msg.from_name,
            )
            for msg in messages
        ]


def _resolve_participants(
    to_addrs,
    cc_addrs,
    from_addr: str | None,
    from_name: str | None,
    owner_email: str,
    system_bot_id: int,
) -> set[int]:
    """Resolve one message's to/cc/from participants to Entity ids."""
    addresses: list[tuple[str, str]] = []
    for addr_list in (to_addrs or []), (cc_addrs or []):
        if isinstance(addr_list, list):
            for entry in addr_list:
                if isinstance(entry, dict):
                    email = (entry.get("address") or "").strip().lower()
                    name = entry.get("name", "") or email
                else:
                    email = str(entry).strip().lower()
                    name = email
                if email:
                    addresses.append((email, name))

    sender_addr = (from_addr or "").strip().lower()
    if sender_addr:
        addresses.append((sender_addr, from_name or sender_addr))

    if owner_email:
        addresses.append((owner_email, owner_email))

    participants: set[int] = set()
    for email, name in addresses:
        source_type = (
            "account_owner" if email == owner_email else "email_contact"
        )
        entity_id = resolve_entity(
            name=name,
            chatbot_id=system_bot_id,
            entity_type="person",
            source_type=source_type,
        )
        if entity_id is not None:
            participants.add(entity_id)
    return participants


def _write_edges(session, participants: set[int]) -> int:
    """Upsert entity_relationships edges for every pair in *participants*.

    Returns the number of edges created/updated.
    """
    if len(participants) < 2:
        return 0

    now = datetime.datetime.utcnow()
    edges = 0
    for a_id, b_id in itertools.combinations(participants, 2):
        if a_id > b_id:
            a_id, b_id = b_id, a_id  # Canonical ordering

        existing = (
            session.query(EntityRelationship)
            .filter(
                EntityRelationship.entity_a_id == a_id,
                EntityRelationship.entity_b_id == b_id,
                EntityRelationship.source == "email_co_occurrence",
            )
            .first()
        )
        if existing:
            existing.evidence_count += 1
            existing.last_observed_at = now
        else:
            session.add(EntityRelationship(
                entity_a_id=a_id,
                entity_b_id=b_id,
                evidence_count=1,
                source="email_co_occurrence",
                first_observed_at=now,
                last_observed_at=now,
            ))
        edges += 1

    return edges


def _batch_mark_processed(
    session,
    message_ids: list[int],
) -> None:
    """Set co_occurrence_processed_at on all listed messages in one
    batch UPDATE — atomically committed with the calling transaction,
    not in a separate session."""
    if not message_ids:
        return
    now = datetime.datetime.utcnow()
    session.query(EmailMessage).filter(
        EmailMessage.id.in_(message_ids),
    ).update(
        {"co_occurrence_processed_at": now},
        synchronize_session=False,
    )
