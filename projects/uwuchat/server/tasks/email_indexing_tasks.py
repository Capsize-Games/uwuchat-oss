"""Background email body indexing tasks.

This module handles background indexing of email body chunks after the
main sync completes. Indexing is decoupled from "sync complete" so
users can connect immediately without waiting for embedding every
thread.

Architecture:
  - ``_index_email_bodies_background`` runs after ``_sync_callback``
    completes, indexing threads most-recent-first.
  - Uses a bounded ``ThreadPoolExecutor`` to parallelize **batches**
    of threads (not individual threads). Each batch collects all
    message IDs for its threads, fetches them in one multi-batch JMAP
    call, then embeds all chunks across all threads in a handful of
    batched embedding calls (see ``email_body_indexer.py``).
  - Progress is emitted via the existing ``emit_progress`` pattern
    on a separate track from the main sync bar.
  - Idempotent per-thread: re-running the task picks up where it left
    off via the same "threads needing reindex" query.
  - Threads needing indexing include both never-indexed threads and
    threads that have received new messages since their last index.
"""

from __future__ import annotations

import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from celery.utils.log import get_task_logger

from airunner_services.tasks.celery_app import app

logger = get_task_logger(__name__)

# Number of threads to process in a single batch submission to the
# thread pool.  Each batch collects *all* message IDs across its
# threads and fetches them in one multi-batch JMAP call, then embeds
# all chunks across all threads in a handful of batched embedding
# calls.
#
# 250 threads is a reasonable middle ground:
#   - ~3 messages/thread × 250 threads = ~750 message IDs
#   - At 250 IDs/JMAP request (sync_body_fetch._BATCH_SIZE), that
#     becomes 3 concurrent requests — well under Fastmail's 10-request
#     global ceiling, especially with the global semaphore guarding it.
#   - ~3 chunks/thread × 250 threads = ~750 chunks
#   - At 500 chunks/embedding call (email_body_indexer._EMBEDDING_BATCH_SIZE),
#     that becomes 2 embedding API calls instead of 250.
_THREAD_BATCH_SIZE = 250

# Conservative default worker count for embedding API calls.
# Each worker now processes _THREAD_BATCH_SIZE threads per submission
# (not 1), so the total parallelism in flight is
#   _EMBEDDING_WORKER_COUNT × _THREAD_BATCH_SIZE
# = 4 × 250 = 1,000 threads at any given time.
#
# The global JMAP concurrency gate (threading.Semaphore with value 10
# in sync_body_fetch.py) bounds the actual outbound HTTP concurrency,
# so we can tune the worker count independently for reasonable CPU
# parallelism without needing to encode Fastmail's limit here.
_EMBEDDING_WORKER_COUNT = 4


def _fetch_and_index_thread_batch(
    email_account_id: int,
    thread_ids: list[str],
    provider,
    account_id: int,
    tenant_key: str,
    dek: bytes,
    on_progress,
) -> None:
    """Fetch a batch of threads' real body content via the JMAP provider,
    then chunk, embed, and persist all of them.

    Replaces the per-thread worker.  Runs inside a ThreadPoolExecutor
    worker, which starts with no tenant/DEK context of its own — each
    worker enters its own scope from the plain *tenant_key* / *dek*
    arguments passed through as function parameters (see constraint #2
    in the design plan).

    The database's ``EmailMessage`` model is metadata-only — it has
    no body text column, by design (bodies aren't persisted in
    plaintext). The real content has to come from a live provider
    fetch, not from querying that table directly.
    """
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.models.email_message import (
        EmailMessage,
    )
    from airunner_services.database.session import session_scope
    from airunner_services.utils.crypto.dek_cache import dek_scope
    from projects.uwuchat.server.email.email_body_indexer import (
        index_thread_bodies,
    )
    from projects.uwuchat.server.email.sync_body_fetch import (
        fetch_email_bodies,
    )

    with tenant_scope(tenant_key), dek_scope(dek):
        # Single batched query for all provider_message_ids across
        # all threads in this batch.
        with session_scope() as session:
            provider_message_ids = set(
                r[0] for r in session.query(
                    EmailMessage.provider_message_id,
                ).filter(
                    EmailMessage.email_account_id == email_account_id,
                    EmailMessage.thread_id.in_(thread_ids),
                    EmailMessage.deleted == False,
                ).all()
            )

        if not provider_message_ids:
            return

        # Single fetch call for ALL message IDs — the internal
        # batching in sync_body_fetch.py now gets a meaningful number
        # of IDs (typically ~750) split into ~3 concurrent JMAP
        # requests, bounded by the global threading.Semaphore.
        messages = fetch_email_bodies(provider, provider_message_ids)
        if not messages:
            return

        # Pass ALL messages spanning many threads to the batch-aware
        # indexer, which groups by thread internally and embeds all
        # chunks in batch embedding calls.
        index_thread_bodies(
            email_account_id, messages,
            on_progress=on_progress, account_id=account_id,
        )


@app.task(
    bind=True,
    name="projects.uwuchat.server.tasks.email_indexing_tasks._index_email_bodies_background",
    queue="sync",
)
def _index_email_bodies_background(
    self,
    email_account_id: int,
    user_id: int,
    tenant_key: str,
    account_id: int,
) -> dict:
    """Background task to index email body chunks.

    Runs after the main sync completes (marked "connected"). Indexes
    threads most-recent-first (by ``EmailMessage.sent_at`` descending).

    Uses a bounded thread pool to parallelize embedding calls. Each
    thread's chunks are embedded in one batched API call.

    Progress is emitted via ``emit_progress`` on a separate track
    from the main sync bar. The task is idempotent: re-running it
    picks up where it left off via the existing delete-then-reinsert
    pattern in ``email_body_indexer.py::_compute_and_persist``.

    Respects ``sync_cancellation.is_cancelled`` between threads so a
    disconnect stops indexing promptly.
    """
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.models.email_body_chunk import (
        EmailBodyChunk,
    )
    from airunner_services.database.models.email_message import (
        EmailMessage,
    )
    from airunner_services.database.session import session_scope
    from airunner_services.tasks.task_helpers import task_dek_scope
    from sqlalchemy import func

    from projects.uwuchat.server.email.sync_cancellation import (
        is_cancelled,
    )
    from projects.uwuchat.server.email.sync_progress_events import (
        emit_progress,
    )
    from projects.uwuchat.server.email.sync_progress_store import (
        email_sync_progress_set_total,
    )

    from airunner_services.database.models.email_account import (
        EmailAccount,
    )

    job_id = self.request.id or f"email-index-{email_account_id}"

    with task_dek_scope(tenant_key, account_id) as dek:
        if dek is None:
            logger.info(
                "DEK relay empty for background indexing of account %d",
                account_id,
            )
            # Mark indexing as pending so a later live session can
            # retry background indexing. Bulk UPDATE rather than
            # loading the full entity — there's no DEK active here,
            # and EmailAccount.credential_ciphertext is decrypted
            # eagerly on row-fetch, which would raise
            # DataEncryptionError for exactly the accounts this
            # branch needs to handle gracefully.
            with tenant_scope(tenant_key):
                with session_scope() as session:
                    session.query(EmailAccount).filter(
                        EmailAccount.id == email_account_id,
                    ).update(
                        {"indexing_status": "pending"},
                        synchronize_session=False,
                    )
                    session.commit()
            return {"status": "skipped", "reason": "no_dek"}

        with tenant_scope(tenant_key):
            with session_scope() as session:
                from airunner_services.database.models.email_account import (
                    EmailAccount,
                )

                # Column-only scalar: a full-entity load here was
                # read outside this session block (after commit +
                # close), which raises DetachedInstanceError on the
                # next attribute access — a plain bool/None survives
                # the session boundary fine.
                account_deleted = (
                    session.query(EmailAccount.deleted)
                    .filter(EmailAccount.id == email_account_id)
                    .scalar()
                )

            if account_deleted is None or account_deleted:
                logger.info(
                    "Account %d not found or deleted, skipping indexing",
                    email_account_id,
                )
                return {"status": "cancelled", "reason": "account_deleted"}

            # Build a live JMAP provider from the account's decrypted
            # credential — required to fetch real body content below.
            # A column-only scalar still respects credential_ciphertext's
            # UserEncryptedText decryption; a live DEK is active here
            # (we're past the `if dek is None` guard above).
            with session_scope() as session:
                token = (
                    session.query(EmailAccount.credential_ciphertext)
                    .filter(EmailAccount.id == email_account_id)
                    .scalar()
                )

            if not token:
                logger.info(
                    "No credential available for account %d, "
                    "skipping indexing",
                    email_account_id,
                )
                return {
                    "status": "cancelled", "reason": "no_credential",
                }

            from projects.uwuchat.server.email.fastmail import (
                FastmailJMAPProvider,
            )

            provider = FastmailJMAPProvider(api_token=str(token))

            # Get threads that need indexing: either never indexed or have
            # new messages since their last index.
            with session_scope() as session:
                # Get all threads that have body chunks
                indexed_threads = set(
                    r[0] for r in session.query(EmailBodyChunk.thread_id)
                    .filter(
                        EmailBodyChunk.email_account_id == email_account_id,
                    )
                    .all()
                )

                # Get all threads from messages
                all_threads = set(
                    r[0] for r in session.query(EmailMessage.thread_id)
                    .filter(
                        EmailMessage.email_account_id == email_account_id,
                        EmailMessage.deleted == False,
                    )
                    .all()
                )

                # Never-indexed threads
                never_indexed = all_threads - indexed_threads

                # Threads needing reindex: have existing chunks but also have
                # messages processed after the chunk was last generated.
                # Detected by comparing max(processed_at) vs max(generated_at).
                reindex_needed: set[str] = set()
                if indexed_threads:
                    # Batched query: max chunk generated_at per thread
                    max_gen_rows = (
                        session.query(
                            EmailBodyChunk.thread_id,
                            func.max(EmailBodyChunk.generated_at).label(
                                "max_gen",
                            ),
                        )
                        .filter(
                            EmailBodyChunk.email_account_id
                            == email_account_id,
                            EmailBodyChunk.thread_id.in_(indexed_threads),
                        )
                        .group_by(EmailBodyChunk.thread_id)
                        .all()
                    )
                    thread_max_gen = {
                        r[0]: r[1] for r in max_gen_rows
                    }

                    # Batched query: max message processed_at per thread
                    max_proc_rows = (
                        session.query(
                            EmailMessage.thread_id,
                            func.max(EmailMessage.processed_at).label(
                                "max_proc",
                            ),
                        )
                        .filter(
                            EmailMessage.email_account_id
                            == email_account_id,
                            EmailMessage.thread_id.in_(indexed_threads),
                            EmailMessage.deleted == False,
                        )
                        .group_by(EmailMessage.thread_id)
                        .all()
                    )
                    thread_max_proc = {
                        r[0]: r[1] for r in max_proc_rows
                    }

                    for tid in indexed_threads:
                        max_gen = thread_max_gen.get(tid)
                        max_proc = thread_max_proc.get(tid)
                        if (
                            max_gen is not None
                            and max_proc is not None
                            and max_proc > max_gen
                        ):
                            reindex_needed.add(tid)

                # Threads with a chunk row but no usable embedding —
                # e.g. a transient embedding-provider failure (rate
                # limit, timeout) that fell through to the None
                # fallback in _compute_encrypted_embeddings. The
                # timestamp comparison above can't catch this (the
                # chunk's generated_at is fine, its content just
                # never got embedded), so this needs its own check —
                # otherwise a chunk that failed to embed once stays
                # permanently unsearchable, since nothing else would
                # ever re-select it for reindexing.
                failed_embedding_threads = set(
                    r[0] for r in session.query(EmailBodyChunk.thread_id)
                    .filter(
                        EmailBodyChunk.email_account_id == email_account_id,
                        EmailBodyChunk.thread_id.in_(indexed_threads),
                        EmailBodyChunk.embedding_enc.is_(None),
                    )
                    .distinct()
                    .all()
                ) if indexed_threads else set()

                threads_needing_index = (
                    never_indexed | reindex_needed
                    | failed_embedding_threads
                )

            if not threads_needing_index:
                logger.info(
                    "No threads need indexing for account %d",
                    email_account_id,
                )
                return {"status": "complete", "threads_indexed": 0}

            # Set total for progress tracking
            email_sync_progress_set_total(
                email_account_id, len(threads_needing_index),
                "Background indexing email bodies…",
            )

            # Sort threads by most recent message activity (sent_at descending)
            # so newest threads are indexed first.  Uses a single batched
            # query instead of N+1 per-thread queries.
            with session_scope() as session:
                latest_msg_rows = (
                    session.query(
                        EmailMessage.thread_id,
                        func.max(EmailMessage.sent_at).label("latest"),
                    )
                    .filter(
                        EmailMessage.email_account_id == email_account_id,
                        EmailMessage.thread_id.in_(threads_needing_index),
                        EmailMessage.deleted == False,
                    )
                    .group_by(EmailMessage.thread_id)
                    .all()
                )
                thread_latest = {
                    r[0]: r[1] for r in latest_msg_rows
                }
                sorted_threads = sorted(
                    threads_needing_index,
                    key=lambda tid: thread_latest.get(tid)
                    or datetime.datetime.min,
                    reverse=True,
                )

            total_threads = len(sorted_threads)
            # Thread-safe counter for cumulative progress across pool workers
            import threading
            _progress_lock = threading.Lock()
            _threads_done = 0

            def _on_thread_done(cur: int, tot: int) -> None:
                """Called per-thread from inside index_thread_bodies.
                Updates a cumulative counter so progress shows actual
                "N of total threads indexed" rather than per-thread 1/1."""
                nonlocal _threads_done
                with _progress_lock:
                    _threads_done += 1
                    emit_progress(
                        email_account_id,
                        "Indexing email bodies (background)",
                        _threads_done, total_threads,
                        unit="threads",
                    )

            # Use a bounded thread pool for parallel embedding calls.
            # I/O-bound work (HTTP calls) releases the GIL, so a thread pool
            # is appropriate here (not a process pool).
            #
            # Each submission is a **batch** of threads
            # (``_THREAD_BATCH_SIZE``), not a single thread — the batch worker
            # fetches all message IDs across the batch in one multi-batch JMAP
            # call and passes all resulting messages to the batch-aware indexer.
            #
            # ContextVars (tenant_key, the active DEK) do NOT propagate
            # into ThreadPoolExecutor worker threads by default — each
            # worker starts with an empty context. A single shared
            # contextvars.Context can't fix this either: Context.run()
            # can only be entered by one thread at a time, so every
            # worker but the first would raise "cannot enter context
            # ... already entered". Instead, pass the plain tenant_key
            # and dek values through and have each worker independently
            # enter its own scope (see _fetch_and_index_thread_batch).
            thread_batches = [
                sorted_threads[i:i + _THREAD_BATCH_SIZE]
                for i in range(
                    0, len(sorted_threads), _THREAD_BATCH_SIZE,
                )
            ]

            with ThreadPoolExecutor(
                max_workers=_EMBEDDING_WORKER_COUNT,
            ) as executor:
                futures = []
                for batch in thread_batches:
                    if is_cancelled(email_account_id):
                        break

                    future = executor.submit(
                        _fetch_and_index_thread_batch,
                        email_account_id,
                        batch,
                        provider,
                        account_id,
                        tenant_key,
                        dek,
                        _on_thread_done,
                    )
                    futures.append(future)

                # Wait for futures to complete, handling cancellation
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        logger.error(
                            "Background indexing failed for account %d: %s",
                            email_account_id, exc, exc_info=True,
                        )

            # Update progress to complete
            emit_progress(
                email_account_id,
                "Background indexing complete",
                _threads_done, total_threads,
                unit="threads",
            )

            # Mark indexing complete so the pending-indexing retry
            # hook knows this account no longer needs attention.
            with session_scope() as session:
                acct = session.query(EmailAccount).get(
                    email_account_id,
                )
                if acct is not None:
                    acct.indexing_status = "complete"
                    acct.last_indexed_at = datetime.datetime.utcnow()
                    session.commit()

            logger.info(
                "Background indexing complete for account %d: %d/%d threads",
                email_account_id, _threads_done, total_threads,
            )

            return {
                "status": "complete",
                "threads_indexed": _threads_done,
                "total_threads": total_threads,
            }
