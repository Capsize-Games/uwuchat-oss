"""Phases 2–4 processing pipeline — wires preprocessor, body indexer,
and extractor into the sync flow.

Email bodies are fetched, chunked, embedded, and persisted (per-user
encrypted — see ``email_body_indexer.py``) in ``_MSG_CHUNK_SIZE``
chunks end to end (fetch -> contacts -> index -> mark processed), so
``processed_at`` advances incrementally and an interruption loses at
most one chunk's work. Also checks ``sync_cancellation.is_cancelled``
between chunks so a mid-run disconnect stops promptly.

Delta-sync: an existing ``EmailBodyChunk`` triggers a full thread
refetch so the new index covers all messages, not just new ones.

Background indexing: after the main sync completes (marked "connected"),
a separate background task indexes email bodies. This decouples
"connected" from "fully searchable" — users can connect immediately
without waiting for embedding every thread. The background task
indexes threads most-recent-first and uses parallel embedding calls.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from airunner_services.database.models.email_body_chunk import (
    EmailBodyChunk,
)
from airunner_services.database.models.email_message import EmailMessage
from airunner_services.database.session import session_scope

from .contacts import extract_contacts
from .preprocessor import classify_automated, strip_quoted_content
from .sync_body_fetch import fetch_email_bodies
from .sync_cancellation import is_cancelled
from .sync_progress_events import emit_progress

logger = logging.getLogger(__name__)

_IN_CLAUSE_CHUNK = 5000
_MSG_CHUNK_SIZE = 200


def process_new_messages(
    email_account_id: int,
    user_id: int,
    provider: Any,
) -> None:
    """Run Phases 2–4 on unprocessed email messages, chunk by chunk."""
    unprocessed_ids = _get_unprocessed_ids(email_account_id)
    if not unprocessed_ids:
        return

    total = len(unprocessed_ids)
    logger.info(
        "Processing %d unprocessed messages for account %d",
        total, email_account_id,
    )
    done = 0
    for i in range(0, total, _MSG_CHUNK_SIZE):
        if is_cancelled(email_account_id):
            return
        chunk_ids = unprocessed_ids[i:i + _MSG_CHUNK_SIZE]
        _process_message_chunk(
            email_account_id, user_id, provider, chunk_ids,
        )
        done += len(chunk_ids)
        emit_progress(
            email_account_id, "Processing messages", done, total,
        )

    if is_cancelled(email_account_id):
        return

    # Resumable via its own co_occurrence_processed_at column.
    from .co_occurrence import build_co_occurrence_graph

    edges = build_co_occurrence_graph(email_account_id)
    logger.info("Co-occurrence graph: %d edges touched", edges)


def _process_message_chunk(
    email_account_id: int,
    user_id: int,
    provider: Any,
    chunk_ids: list[str],
) -> None:
    """Fetch, extract, and index one chunk; mark it processed only
    after every step succeeds.

    Raises :class:`DataEncryptionError` when no per-user DEK is
    in context — this covers BOTH the body-chunk write
    (``_compute_and_persist``) and the entity-name write
    (``extract_contacts`` → ``resolve_entity``), preventing silent
    fallback to the global keyring for either.

    Note: Body indexing has been moved to a background task. This
    function now only fetches bodies, extracts contacts, and marks
    messages processed. Indexing happens asynchronously via
    ``_index_email_bodies_background``.
    """
    from airunner_services.utils.crypto.data_encryption import (
        DataEncryptionError,
    )
    from airunner_services.utils.crypto.dek_cache import get_user_dek

    if get_user_dek() is None:
        raise DataEncryptionError(
            "Cannot process message chunk — no DEK in context. "
            "Both Entity.display_name_ct (via contacts.py) and "
            "EmailBodyChunk.content_ciphertext (via "
            "email_body_indexer.py) require per-user envelope "
            "encryption. Ensure the caller is wrapped in "
            "task_dek_scope()."
        )

    threads_needing_reindex = _get_threads_needing_reindex(
        email_account_id, chunk_ids,
    )
    all_ids_to_fetch = set(chunk_ids)
    if threads_needing_reindex:
        all_ids_to_fetch.update(_get_all_message_ids_for_threads(
            email_account_id, threads_needing_reindex,
        ))

    all_emails = fetch_email_bodies(provider, all_ids_to_fetch)
    for em in all_emails:
        em.body_text = strip_quoted_content(em.body_text or "")
        em.is_automated = classify_automated(em)

    _update_automated_flags(email_account_id, all_emails)

    # Automated senders (newsletters, no-reply, notifications) are not
    # real connections — extracting them as contacts is what made the
    # network graph balloon into thousands of one-off, edge-less nodes.
    non_automated = [e for e in all_emails if not e.is_automated]
    extract_contacts(email_account_id, user_id, non_automated)

    # Body indexing has been moved to a background task. We no longer
    # call index_thread_bodies here — that happens asynchronously via
    # _index_email_bodies_background after the main sync completes.
    # This keeps the per-chunk loop fast and non-blocking.

    _mark_processed(email_account_id, chunk_ids)


# ---- Helpers --------------------------------------------------------------


def _chunked(ids, size: int = _IN_CLAUSE_CHUNK):
    """Yield *ids* in chunks, staying under Postgres's 65535-param
    bind limit when used inside an ``IN (...)`` clause."""
    ids = list(ids)
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


def _get_unprocessed_ids(email_account_id: int) -> list[str]:
    """Return provider_message_ids for unprocessed messages, ordered
    deterministically so chunk boundaries stay stable across retries."""
    with session_scope() as session:
        rows = (
            session.query(EmailMessage.provider_message_id)
            .filter(
                EmailMessage.email_account_id == email_account_id,
                EmailMessage.processed_at.is_(None),
                EmailMessage.deleted == False,
            )
            .order_by(EmailMessage.id)
            .all()
        )
        return [r[0] for r in rows]


def _get_threads_needing_reindex(
    email_account_id: int,
    unprocessed_ids: list[str],
) -> set[str]:
    """Return thread_ids among unprocessed messages that already have
    body-chunk rows (i.e. need reindexing, not first-time)."""
    with session_scope() as session:
        touched: set[str] = set()
        for chunk in _chunked(unprocessed_ids):
            touched.update(
                r[0] for r in session.query(EmailMessage.thread_id)
                .filter(
                    EmailMessage.email_account_id == email_account_id,
                    EmailMessage.provider_message_id.in_(chunk),
                ).all() if r[0]
            )
        if not touched:
            return set()
        existing: set[str] = set()
        for chunk in _chunked(touched):
            existing.update(
                r[0] for r in session.query(EmailBodyChunk.thread_id)
                .filter(
                    EmailBodyChunk.email_account_id
                    == email_account_id,
                    EmailBodyChunk.thread_id.in_(chunk),
                ).all()
            )
        return existing


def _get_all_message_ids_for_threads(
    email_account_id: int,
    thread_ids: set[str],
) -> set[str]:
    """Return ALL provider_message_ids for the given threads."""
    with session_scope() as session:
        result: set[str] = set()
        for chunk in _chunked(thread_ids):
            result.update(
                r[0] for r in session.query(
                    EmailMessage.provider_message_id,
                ).filter(
                    EmailMessage.email_account_id == email_account_id,
                    EmailMessage.thread_id.in_(chunk),
                    EmailMessage.deleted == False,
                ).all()
            )
        return result


def _update_automated_flags(
    email_account_id: int,
    emails: list,
) -> None:
    """Persist is_automated classifications to email_messages."""
    automated_ids = {e.provider_id for e in emails if e.is_automated}
    if not automated_ids:
        return
    with session_scope() as session:
        for chunk in _chunked(automated_ids):
            session.query(EmailMessage).filter(
                EmailMessage.email_account_id == email_account_id,
                EmailMessage.provider_message_id.in_(chunk),
            ).update(
                {"is_automated": True},
                synchronize_session=False,
            )
        session.commit()


def _mark_processed(
    email_account_id: int,
    provider_ids: list[str],
) -> None:
    """Set processed_at on all listed messages."""
    now = datetime.datetime.utcnow()
    with session_scope() as session:
        for chunk in _chunked(provider_ids):
            session.query(EmailMessage).filter(
                EmailMessage.email_account_id == email_account_id,
                EmailMessage.provider_message_id.in_(chunk),
            ).update(
                {"processed_at": now},
                synchronize_session=False,
            )
        session.commit()
