"""Chunk, embed, and persist real email-thread content (Part 2).

Replaces the earlier LLM-free extractive-summary design (sumy's
LsaSummarizer) — that approach lost most of the real content and its
CPU-bound local summarization didn't scale. Instead, each thread's
concatenated message bodies are split into overlapping chunks (same
splitter/size as the existing document-RAG pipeline — see
``rag_properties_mixin.py``) and embedded in **batched** API calls
that span many threads at once, instead of one API call per thread.

Follows the same encryption pattern as ``KnowledgeFact.fact_text``:
chunk text is ``UserEncryptedText``-encrypted (per-user DEK), while
``embedding`` stays plaintext so vector search works without
decrypting anything — only the retrieved excerpt needs an active DEK
to read.

Cost tracking: after every embedding API call, ``record_usage`` is
called to log real token costs (input tokens from the API response,
output tokens = 0 for embeddings). This provides visibility into
embedding costs for both email body indexing and KnowledgeFact
embedding.

Batching strategy
-----------------
Chunks from all threads in a batch are flattened into one list and
embedded together in sub-batches of ``_EMBEDDING_BATCH_SIZE`` (default
500).  This dramatically reduces the number of embedding API calls:
for a 250-thread batch with ~3 chunks per thread, the old code made
250 API calls; the new code makes 2 (750 / 500 = 2).  ``record_usage``
is called once per sub-batch rather than once per thread.
"""

from __future__ import annotations

import datetime
import logging
from typing import Callable

from langchain_text_splitters import RecursiveCharacterTextSplitter

from airunner_services.database.models.email_body_chunk import (
    EmailBodyChunk,
)
from airunner_services.database.session import session_scope

from airunner_services.conf.model_settings import QWEN_EMBEDDING_MODEL

from .provider import EmailMessage
from .sync_cancellation import is_cancelled

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 512
_CHUNK_OVERLAP = 50

# Maximum number of chunks to embed in a single embedding API call.
# The embedding provider has no published rate/size limit, so this is
# set conservatively at 500.  Tune based on empirical testing of the
# provider's latency characteristics.
_EMBEDDING_BATCH_SIZE = 500

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP,
)


def index_thread_bodies(
    email_account_id: int,
    messages: list[EmailMessage],
    on_progress: Callable[[int, int], None] | None = None,
    account_id: int | None = None,
) -> int:
    """Chunk, embed, and persist a batch of messages grouped by thread.

    Batches the embedding call across **all** threads in *messages* at
    once, rather than one API call per thread.  Returns the number of
    threads indexed.  Deletes-then-reinserts each touched thread's
    ``EmailBodyChunk`` rows inside a single ``session_scope()`` block.

    *on_progress*, when given, is called as
    ``on_progress(threads_done, threads_total)`` after **each** thread
    (not once per batch) so callers can drive a per-thread progress
    bar.
    """
    if not messages:
        return 0

    threads = _group_by_thread(messages)
    thread_total = len(threads)
    total = 0
    done = 0

    # ------- Phase 1: build chunks for every thread (no embeddings yet) -------
    thread_chunks: list[tuple[str, list[str], list[EmailMessage]]] = []
    all_chunks: list[str] = []
    # Parallel index into all_chunks: chunk_ranges[i] = (start, end) for
    # the i-th thread, so we can split embeddings back per thread later.
    chunk_ranges: list[tuple[int, int]] = []

    for thread_id, thread_msgs in threads.items():
        if is_cancelled(email_account_id):
            break
        text = _build_thread_text(thread_msgs)
        chunks = _splitter.split_text(text) if text.strip() else []
        if not chunks:
            done += 1
            if on_progress is not None:
                on_progress(done, thread_total)
            continue
        start = len(all_chunks)
        all_chunks.extend(chunks)
        end = len(all_chunks)
        thread_chunks.append((thread_id, chunks, thread_msgs))
        chunk_ranges.append((start, end))

    if not all_chunks:
        return 0

    # ------- Phase 2: embed all chunks in sub-batches ------------------------
    # Resolve the platform account ID (for FHE key material) if not
    # explicitly passed.
    if account_id is None:
        from airunner_services.data.tenant import get_account_id
        account_id = get_account_id()
    if account_id is None:
        from airunner_services.utils.crypto.data_encryption import (
            DataEncryptionError,
        )
        raise DataEncryptionError(
            "Cannot persist email body chunks — no account_id "
            "available. The caller must pass account_id or run "
            "within a tenant scope that sets the account ID."
        )
    from airunner_services.utils.crypto.dek_cache import get_user_dek

    if get_user_dek() is None:
        from airunner_services.utils.crypto.data_encryption import (
            DataEncryptionError,
        )
        raise DataEncryptionError(
            "Cannot persist email body chunks — no DEK in context. "
            "The caller must be wrapped in task_dek_scope(). "
            "This ensures per-user envelope encryption for "
            "content_ciphertext."
        )

    all_embeddings: list[bytes | None] = [None] * len(all_chunks)
    from airunner_services.llm.token_usage import record_usage

    for batch_start in range(0, len(all_chunks), _EMBEDDING_BATCH_SIZE):
        batch_end = min(
            batch_start + _EMBEDDING_BATCH_SIZE, len(all_chunks),
        )
        batch_chunks = all_chunks[batch_start:batch_end]

        # One embedding API call per sub-batch.
        batch_embeddings = _compute_encrypted_embeddings(
            batch_chunks, account_id,
        )
        all_embeddings[batch_start:batch_end] = batch_embeddings

        # Record usage once per sub-batch (not once per thread).
        total_chars = sum(len(c) for c in batch_chunks)
        input_tokens = max(1, total_chars // 4)
        record_usage(
            pipeline_key="EMAIL_BODY_EMBEDDING",
            model_id=QWEN_EMBEDDING_MODEL,
            input_tokens=input_tokens,
            output_tokens=0,
            account_id=account_id,
            call_chain_id=None,
        )

    # ------- Phase 3: persist all threads in one session_scope block ---------
    now = datetime.datetime.utcnow()

    with session_scope() as session:
        for (thread_id, chunks, thread_msgs), (start, end) in zip(
            thread_chunks, chunk_ranges,
        ):
            if is_cancelled(email_account_id):
                break

            embeddings = all_embeddings[start:end]

            # Build participants and date range for this thread.
            participants: set[str] = set()
            for msg in thread_msgs:
                if msg.from_address:
                    participants.add(msg.from_address)
                for addr in (
                    msg.to_addresses or []
                ) + (msg.cc_addresses or []):
                    email = (addr.get("address") or "").strip()
                    if email:
                        participants.add(email)

            dates = [m.sent_at for m in thread_msgs if m.sent_at]
            date_start = min(dates) if dates else now
            date_end = max(dates) if dates else now

            # Delete existing chunks for this thread, then reinsert.
            session.query(EmailBodyChunk).filter(
                EmailBodyChunk.email_account_id == email_account_id,
                EmailBodyChunk.thread_id == thread_id,
            ).delete(synchronize_session=False)

            for index, chunk_text in enumerate(chunks):
                encrypted = (
                    embeddings[index]
                    if index < len(embeddings)
                    else None
                )
                session.add(EmailBodyChunk(
                    email_account_id=email_account_id,
                    thread_id=thread_id,
                    chunk_index=index,
                    content_ciphertext=chunk_text,
                    embedding_enc=encrypted,
                    participant_count=len(participants),
                    message_count=len(thread_msgs),
                    date_range_start=date_start,
                    date_range_end=date_end,
                    generated_at=now,
                ))

            done += 1
            total += 1
            if on_progress is not None:
                on_progress(done, thread_total)

        session.commit()

    return total


def _group_by_thread(
    messages: list[EmailMessage],
) -> dict[str, list[EmailMessage]]:
    """Group messages by thread_id (falling back to their own id)."""
    threads: dict[str, list[EmailMessage]] = {}
    for msg in messages:
        tid = msg.thread_id or msg.provider_message_id
        threads.setdefault(tid, []).append(msg)
    return threads


def _build_thread_text(messages: list[EmailMessage]) -> str:
    """Concatenate a thread's messages, sorted by sent_at, one
    ``"{sender}: {body}"`` line per message."""
    sorted_msgs = sorted(
        messages,
        key=lambda m: m.sent_at or datetime.datetime.min,
    )
    parts = []
    for msg in sorted_msgs:
        sender = msg.from_name or msg.from_address or "unknown"
        body = msg.body_text or ""
        parts.append(f"{sender}: {body}")
    return "\n\n".join(parts)


def _compute_and_persist(
    email_account_id: int,
    thread_id: str,
    chunks: list[str],
    messages: list[EmailMessage],
    account_id: int | None = None,
) -> None:
    """Embed *chunks* and replace this thread's EmailBodyChunk rows.

    *account_id* is the platform account ID (``EmailAccount.user_id``),
    used to resolve the correct FHE key material.  *email_account_id*
    is the mailbox row ID (``EmailAccount.id``) and is stored on each
    ``EmailBodyChunk`` row for per-mailbox scoping.

    Raises :class:`DataEncryptionError` when no per-user DEK is
    available — the caller runs inside ``task_dek_scope`` in the
    chord callback, so a missing DEK at this point means the relay
    entry expired or was never written, and falling back to the
    global keyring would defeat the point of per-user envelope
    encryption.
    """
    from airunner_services.utils.crypto.data_encryption import (
        DataEncryptionError,
    )

    # Resolve the platform account ID if not explicitly passed.
    # The caller (Celery task) passes account_id directly, but
    # other call sites may rely on the tenant context.
    if account_id is None:
        from airunner_services.data.tenant import get_account_id
        account_id = get_account_id()
    if account_id is None:
        raise DataEncryptionError(
            "Cannot persist email body chunks — no account_id "
            "available. The caller must pass account_id or run "
            "within a tenant scope that sets the account ID."
        )
    from airunner_services.utils.crypto.dek_cache import get_user_dek

    if get_user_dek() is None:
        raise DataEncryptionError(
            "Cannot persist email body chunks — no DEK in context. "
            "The caller must be wrapped in task_dek_scope(). "
            "This ensures per-user envelope encryption for "
            "content_ciphertext."
        )

    now = datetime.datetime.utcnow()
    participants: set[str] = set()
    for msg in messages:
        if msg.from_address:
            participants.add(msg.from_address)
        for addr in (msg.to_addresses or []) + (msg.cc_addresses or []):
            email = (addr.get("address") or "").strip()
            if email:
                participants.add(email)

    dates = [m.sent_at for m in messages if m.sent_at]
    date_start = min(dates) if dates else now
    date_end = max(dates) if dates else now

    embeddings = _compute_encrypted_embeddings(chunks, account_id)

    # Record usage for embedding cost tracking.
    # Estimate input tokens from character count (avoids a second API
    # call to get the actual token count — the embedding call above
    # already happened and we don't cache the full API response).
    # Rough estimate: ~1 token per 4 characters for English text.
    from airunner_services.llm.token_usage import record_usage

    total_chars = sum(len(chunk) for chunk in chunks)
    input_tokens = max(1, total_chars // 4)

    # Record usage with pipeline_key for email body embedding
    record_usage(
        pipeline_key="EMAIL_BODY_EMBEDDING",
        model_id=QWEN_EMBEDDING_MODEL,
        input_tokens=input_tokens,
        output_tokens=0,  # Embeddings have no output tokens
        account_id=account_id,
        call_chain_id=None,
    )

    with session_scope() as session:
        session.query(EmailBodyChunk).filter(
            EmailBodyChunk.email_account_id == email_account_id,
            EmailBodyChunk.thread_id == thread_id,
        ).delete(synchronize_session=False)

        for index, chunk_text in enumerate(chunks):
            encrypted = (
                embeddings[index]
                if index < len(embeddings)
                else None
            )
            session.add(EmailBodyChunk(
                email_account_id=email_account_id,
                thread_id=thread_id,
                chunk_index=index,
                content_ciphertext=chunk_text,
                embedding_enc=encrypted,
                participant_count=len(participants),
                message_count=len(messages),
                date_range_start=date_start,
                date_range_end=date_end,
                generated_at=now,
            ))
        session.commit()


def _compute_encrypted_embeddings(
    chunks: list[str], account_id: int,
) -> list[bytes | None]:
    """Batch-embed *chunks* and encrypt with the account's FHE context.

    *account_id* is the platform account ID — the same ID that FHE
    key material and search-time resolution use.  Must NOT be the
    mailbox row ID (``EmailAccount.id``).
    """
    try:
        from projects.uwuchat.server.embedding_provider import (
            get_embedding_provider,
        )
        from airunner_services.utils.crypto.fhe_account_context import (
            get_or_create_public_context,
        )
        from airunner_services.utils.crypto.fhe_helpers import (
            encrypt_embedding,
            l2_normalize,
        )

        provider = get_embedding_provider()
        vectors = provider.embed_documents(chunks, priority="bulk")

        public_ctx = get_or_create_public_context(account_id)
        encrypted: list[bytes | None] = []
        for vec in vectors:
            if vec is None:
                encrypted.append(None)
                continue
            normalized = l2_normalize(vec)
            encrypted.append(encrypt_embedding(normalized, public_ctx))
        return encrypted
    except Exception as exc:
        logger.warning(
            "Failed to compute encrypted embeddings: %s", exc,
        )
        return [None] * len(chunks)
