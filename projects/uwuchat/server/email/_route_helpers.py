"""Shared helpers for email routes — cascade delete, token validation."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_FASTMAIL_SESSION_URL = "https://api.fastmail.com/jmap/session"


async def validate_fastmail_token(token: str) -> str | None:
    """Validate a Fastmail API token via the JMAP session endpoint.

    Returns the account's primary email address on success, or None.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                _FASTMAIL_SESSION_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Fastmail session validation returned %d",
                    resp.status_code,
                )
                return None
            data = resp.json()
            primary = (
                data.get("primaryAccounts", {})
                .get("urn:ietf:params:jmap:mail", "")
            )
            acct = data.get("accounts", {}).get(primary, {})
            return acct.get("name", "") or None
    except Exception as exc:
        logger.warning("Fastmail session validation error: %s", exc)
        return None


def cascade_delete_email_data(
    session,
    email_account_id: int,
    user_id: int,
) -> None:
    """Delete all derived data for one email account.

    Covers: email_messages, email_body_chunks, email_contacts,
    email_stats, email_sync_checkpoints, entities,
    entity_relationships (edges from email co-occurrence),
    and knowledge_facts rows with data_source='email'.
    """
    from airunner_services.database.models.email_body_chunk import (
        EmailBodyChunk,
    )
    from airunner_services.database.models.email_contact import (
        EmailContact,
    )
    from airunner_services.database.models.email_message import (
        EmailMessage,
    )
    from airunner_services.database.models.email_stats import (
        EmailStats,
    )
    from airunner_services.database.models.email_sync_checkpoint import (
        EmailSyncCheckpoint,
    )
    from airunner_services.database.models.knowledge_fact import (
        KnowledgeFact,
    )

    # Snapshot contact IDs before deleting rows they reference.
    contact_ids = _snapshot_email_contact_ids(session, user_id)

    for model in (
        EmailMessage, EmailBodyChunk, EmailStats,
        EmailSyncCheckpoint,
    ):
        session.query(model).filter(
            model.email_account_id == email_account_id,
        ).delete(synchronize_session=False)

    session.query(EmailContact).filter(
        EmailContact.user_id == user_id,
    ).delete(synchronize_session=False)

    _delete_email_entity_graph(session, contact_ids)

    system_bot_id = _get_system_bot_id(session)
    if system_bot_id is not None:
        session.query(KnowledgeFact).filter(
            KnowledgeFact.chatbot_id == system_bot_id,
            KnowledgeFact.data_source == "email",
        ).delete(synchronize_session=False)


def _snapshot_email_contact_ids(session, user_id: int) -> set[int]:
    """Return the set of EmailContact.id values for *user_id*."""
    from airunner_services.database.models.email_contact import (
        EmailContact,
    )

    rows = (
        session.query(EmailContact.id)
        .filter(EmailContact.user_id == user_id)
        .all()
    )
    return {row[0] for row in rows}


def _delete_email_entity_graph(
    session,
    contact_ids: set[int],
) -> None:
    """Delete Entity and EntityRelationship rows built from email data."""
    from airunner_services.database.models.entity import Entity
    from airunner_services.database.models.entity_relationship import (
        EntityRelationship,
    )

    if not contact_ids:
        return

    entity_ids = {
        row[0]
        for row in session.query(Entity.id)
        .filter(
            Entity.source_ref_table == "email_contacts",
            Entity.source_ref_id.in_(contact_ids),
        )
        .all()
    }

    if entity_ids:
        session.query(EntityRelationship).filter(
            EntityRelationship.source == "email_co_occurrence",
            EntityRelationship.entity_a_id.in_(entity_ids)
            | EntityRelationship.entity_b_id.in_(entity_ids),
        ).delete(synchronize_session=False)

        session.query(Entity).filter(
            Entity.id.in_(entity_ids),
        ).delete(synchronize_session=False)


def _get_system_bot_id(session) -> int | None:
    """Return the system bot's stable chatbot ID for this tenant."""
    from airunner_services.database.models.chatbot import Chatbot

    bot = (
        session.query(Chatbot)
        .filter(Chatbot.is_system_bot.is_(True))
        .first()
    )
    return bot.id if bot else None
