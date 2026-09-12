"""Email sync Celery task definitions.

Architecture:
  ``sync_email_account`` (parent) dispatches ``_sync_one_mailbox``
  (children) independently, then enqueues ``_await_mailbox_sync`` to
  poll the durable ``EmailSyncCheckpoint`` table until every mailbox
  reports done, at which point it dispatches ``_sync_callback``
  (process_new_messages + background indexing).

  Deliberately NOT a Celery ``chord``: a chord's redis backend tracks
  completion via an in-memory counter keyed off the exact number of
  header tasks published. If even one of those publishes is dropped
  (a broker hiccup during the burst-publish of N tasks — observed in
  production: 35 dispatched, only 34 ever tracked), the counter can
  never reach its target and the callback silently never fires, with
  no error anywhere — the sync just hangs forever. Polling durable
  DB state sidesteps that failure mode entirely and is resumable: a
  worker restart mid-poll just re-schedules the same check.

  Background indexing: after ``_sync_callback`` marks the account
  "connected", a separate task ``_index_email_bodies_background``
  indexes email bodies asynchronously. This decouples "connected"
  from "fully searchable" — users can connect immediately without
  waiting for embedding every thread.
"""

from __future__ import annotations

import logging

from celery.utils.log import get_task_logger

from airunner_services.tasks.celery_app import app

logger = get_task_logger(__name__)

# How often _await_mailbox_sync re-checks checkpoint completion, and
# the ceiling on how long it will wait before surfacing a real error
# instead of hanging silently forever like the old chord did.
_POLL_INTERVAL_SECONDS = 15
_MAX_POLL_ATTEMPTS = 240  # 240 * 15s = 1 hour


# -- Parent task: sync one email account ------------------------------------


@app.task(
    bind=True,
    name="projects.uwuchat.server.tasks.email_tasks.sync_email_account",
    max_retries=2,
    default_retry_delay=600,  # 10 min
    queue="sync",
)
def sync_email_account(
    self,
    email_account_id: int,
    tenant_key: str,
    account_id: int,
) -> dict:
    """Sync one email account: dispatch per-mailbox tasks independently.

    Parameters are passed explicitly (not via contextvars) because
    Celery tasks run in separate worker processes across a broker
    round-trip:

    *email_account_id*: the EmailAccount.id
    *tenant_key*: tenant schema identifier
    *account_id*: the user's account.id (for DEK relay lookup)
    """
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.models.email_account import (
        EmailAccount,
    )
    from airunner_services.database.session import session_scope
    from airunner_services.tasks.task_helpers import task_dek_scope

    job_id = self.request.id or f"email-sync-{email_account_id}"
    logger.info(
        "Email sync task started: account=%d tenant=%s job=%s",
        email_account_id, tenant_key, job_id,
    )

    from airunner_services.tasks.redis_client import dek_relay_delete

    from projects.uwuchat.server.email.sync_cancellation import (
        finish_sync,
    )
    from projects.uwuchat.server.email.sync_progress_events import (
        emit_complete,
    )
    from projects.uwuchat.server.email.sync_progress_store import (
        email_sync_progress_set_total,
    )

    # peek=True: the DEK relay entry must survive this parent task,
    # since the fanned-out _sync_one_mailbox children, the
    # _sync_callback callback, and (downstream of that)
    # _index_email_bodies_background all need to read it too.
    # _index_email_bodies_background is the true last consumer and
    # reads it in the default (non-peek, read-and-delete) mode, so it
    # cleans up the entry itself — every earlier consumer in this
    # chain must use peek=True. The dek_relay_delete calls below cover
    # this task's own early-exit paths, where nothing downstream will
    # ever run to consume the entry otherwise.
    with task_dek_scope(tenant_key, account_id, peek=True) as dek:
        if dek is None:
            # Not a user-facing failure — the periodic Beat trigger
            # runs unattended with no live DEK by design (see
            # periodic_tasks.py's skip-and-defer docstring). Do NOT
            # call emit_complete here: it would overwrite whatever
            # completion state the last *real* (connect-triggered)
            # sync left behind with a scary "failed" banner, even
            # though nothing actually went wrong.
            logger.info(
                "DEK relay empty for account %d — "
                "skipping (will retry on next live session)",
                account_id,
            )
            finish_sync(email_account_id)
            return {"status": "skipped", "reason": "no_dek"}

        with tenant_scope(tenant_key):
            with session_scope() as session:
                account = (
                    session.query(EmailAccount)
                    .get(email_account_id)
                )
                if account is None or account.deleted:
                    emit_complete(
                        email_account_id, False,
                        "Account not found or deleted",
                    )
                    finish_sync(email_account_id)
                    dek_relay_delete(account_id)
                    return {
                        "status": "error",
                        "reason": "Account not found or deleted",
                    }

                token = account.credential_ciphertext
                if not token:
                    emit_complete(
                        email_account_id, False, "No credential stored",
                    )
                    finish_sync(email_account_id)
                    dek_relay_delete(account_id)
                    return {
                        "status": "error",
                        "reason": "No credential stored",
                    }

                user_id_val = account.user_id

            from projects.uwuchat.server.email.fastmail import (
                FastmailJMAPProvider,
            )

            provider = FastmailJMAPProvider(api_token=str(token))
            mailboxes = _run_async(provider.list_mailboxes())

            # Probe each mailbox's total upfront (calculateTotal is
            # always requested — see query_email_ids's docstring —
            # so limit=1 is enough to learn the count) so the client
            # gets one accurate account-wide bar from the very first
            # update, instead of a denominator that grows as mailboxes
            # report in.
            total_across_account = 0
            for mailbox in mailboxes:
                probe = _run_async(
                    provider.query_email_ids(
                        mailbox.id, position=0, limit=1,
                    ),
                )
                total_across_account += probe.total or 0
            email_sync_progress_set_total(
                email_account_id, total_across_account,
                "Starting analysis…",
            )

            if not mailboxes:
                emit_complete(
                    email_account_id, True, "No mailboxes found",
                )
                finish_sync(email_account_id)
                dek_relay_delete(account_id)
                return {"status": "complete", "mailboxes": 0}

            # Dispatch each mailbox independently — see the module
            # docstring for why this isn't a chord. _await_mailbox_sync
            # (below) polls EmailSyncCheckpoint for completion and
            # dispatches _sync_callback once every mailbox is done.
            for mailbox in mailboxes:
                _sync_one_mailbox.apply_async(
                    args=[
                        email_account_id, mailbox.id, mailbox.role,
                        mailbox.name, tenant_key, account_id,
                    ],
                    queue="sync",
                )

            _await_mailbox_sync.apply_async(
                args=[
                    email_account_id, user_id_val, tenant_key,
                    account_id, len(mailboxes),
                ],
                queue="sync",
                countdown=_POLL_INTERVAL_SECONDS,
            )

            return {
                "status": "enqueued",
                "mailboxes": len(mailboxes),
            }


# -- Child task: sync one mailbox -------------------------------------------


@app.task(
    bind=True,
    name="projects.uwuchat.server.tasks.email_tasks._sync_one_mailbox",
    queue="sync",
)
def _sync_one_mailbox(
    self,
    email_account_id: int,
    mailbox_id: str,
    mailbox_role: str,
    mailbox_name: str,
    tenant_key: str,
    account_id: int,
) -> dict:
    """Backfill one mailbox: paginate email IDs, persist metadata.

    Mirrors ``_backfill_one_mailbox`` from sync_backfill.py, but
    runs as an independent Celery task so each mailbox can be
    scheduled separately; ``_await_mailbox_sync`` polls
    ``EmailSyncCheckpoint`` to detect when all of them are done.

    *mailbox_id* is the opaque JMAP mailbox ID — used as the
    progress-entry key (stable, unique per mailbox) but never shown
    to the user. *mailbox_name* is the human-readable folder name
    (e.g. "Inbox", "Archive") — used in progress labels.

    *account_id* is the user's account.id, needed to peek the DEK
    relay when reading the account's encrypted credential — this
    task is one of several concurrent consumers of the same relay
    entry (see ``sync_email_account``'s ``peek=True`` comment).
    """
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.models.email_account import (
        EmailAccount,
    )
    from airunner_services.database.models.email_sync_checkpoint import (
        EmailSyncCheckpoint,
    )
    from airunner_services.database.session import session_scope
    from airunner_services.tasks.redis_client import (
        job_progress_write,
    )
    from airunner_services.tasks.task_helpers import task_dek_scope

    from projects.uwuchat.server.email.sync_mailbox_lock import (
        acquire_mailbox_lock,
        release_mailbox_lock,
    )
    from projects.uwuchat.server.email.sync_persist import (
        persist_email_metadata,
    )
    from projects.uwuchat.server.email.sync_progress_events import (
        emit_progress_delta,
    )

    _BATCH_SIZE = 50
    job_id = self.request.id or f"mailbox-{mailbox_id}"

    # A redelivered (duplicate) execution of this same mailbox must
    # not proceed — see sync_mailbox_lock's docstring for why this
    # can happen and why it would otherwise inflate the shared
    # progress counter past its total.
    if not acquire_mailbox_lock(email_account_id, mailbox_id, job_id):
        logger.info(
            "Mailbox %s (account %d) already syncing under another "
            "task execution — skipping duplicate run %s",
            mailbox_id, email_account_id, job_id,
        )
        return {
            "status": "skipped_duplicate",
            "mailbox_id": mailbox_id,
        }

    try:
        with tenant_scope(tenant_key):
            # Load or create checkpoint.
            with session_scope() as session:
                cp = (
                    session.query(EmailSyncCheckpoint)
                    .filter(
                        EmailSyncCheckpoint.email_account_id
                        == email_account_id,
                        EmailSyncCheckpoint.mailbox_id == mailbox_id,
                    )
                    .first()
                )
                is_done = cp is not None and cp.status == "completed"
                position = cp.last_position if cp else 0
                total_processed = cp.emails_processed if cp else 0

            if is_done:
                job_progress_write(
                    job_id,
                    status="complete",
                    current=total_processed,
                    total=total_processed,
                    label=f"{mailbox_name} (already synced)",
                    tenant_key=tenant_key,
                )
                emit_progress_delta(
                    email_account_id,
                    total_processed,
                    f"{mailbox_name} (already synced)",
                )
                return {
                    "status": "complete",
                    "mailbox_id": mailbox_id,
                    "processed": total_processed,
                }

            # Ensure checkpoint row exists.
            with session_scope() as session:
                if cp is None:
                    session.add(EmailSyncCheckpoint(
                        email_account_id=email_account_id,
                        mailbox_id=mailbox_id,
                        mailbox_role=mailbox_role,
                        status="in_progress",
                    ))
                else:
                    row = (
                        session.query(EmailSyncCheckpoint)
                        .filter(
                            EmailSyncCheckpoint.email_account_id
                            == email_account_id,
                            EmailSyncCheckpoint.mailbox_id
                            == mailbox_id,
                        )
                        .first()
                    )
                    if row is not None:
                        row.status = "in_progress"
                session.commit()

            # Re-resolve provider. Reading credential_ciphertext
            # requires an active DEK context (UserEncryptedText
            # decrypts on read), so this must happen inside
            # task_dek_scope — peek=True since sibling mailbox tasks
            # and the callback need the same relay entry too.
            with task_dek_scope(
                tenant_key, account_id, peek=True,
            ) as dek:
                if dek is None:
                    return {
                        "status": "error",
                        "reason": "DEK relay empty",
                    }
                with session_scope() as session:
                    account = session.query(EmailAccount).get(
                        email_account_id,
                    )
                    if (
                        account is None
                        or not account.credential_ciphertext
                    ):
                        return {
                            "status": "error",
                            "reason": "No credential available",
                        }
                    token = account.credential_ciphertext

            from projects.uwuchat.server.email.fastmail import (
                FastmailJMAPProvider,
            )

            provider = FastmailJMAPProvider(api_token=str(token))

            while True:
                page = _run_async(
                    provider.query_email_ids(
                        mailbox_id,
                        position=position,
                        limit=_BATCH_SIZE,
                    ),
                )
                if not page.ids:
                    break

                emails = _run_async(
                    provider.get_emails(page.ids, include_body=False),
                )
                persist_email_metadata(
                    email_account_id, emails, mailbox_role,
                )
                total_processed += len(emails)

                position += len(page.ids)
                _update_checkpoint(
                    email_account_id, mailbox_id, position,
                    total_processed,
                )

                job_progress_write(
                    job_id,
                    status="in_progress",
                    current=total_processed,
                    total=page.total or 0,
                    label=f"Analyzing {mailbox_name}",
                    tenant_key=tenant_key,
                )
                emit_progress_delta(
                    email_account_id, len(emails),
                    f"Analyzing {mailbox_name}",
                )

                if page.total is not None and position >= page.total:
                    break

            _mark_checkpoint_complete(
                email_account_id, mailbox_id, total_processed,
            )

            job_progress_write(
                job_id,
                status="complete",
                current=total_processed,
                total=total_processed,
                label=f"{mailbox_name} complete",
                tenant_key=tenant_key,
            )

            return {
                "status": "complete",
                "mailbox_id": mailbox_id,
                "processed": total_processed,
            }
    finally:
        release_mailbox_lock(email_account_id, mailbox_id, job_id)


# -- Watchdog: poll for mailbox completion, then run the callback -----------


@app.task(
    bind=True,
    name="projects.uwuchat.server.tasks.email_tasks._await_mailbox_sync",
    queue="sync",
)
def _await_mailbox_sync(
    self,
    email_account_id: int,
    user_id: int,
    tenant_key: str,
    account_id: int,
    expected_mailboxes: int,
    attempt: int = 0,
) -> dict:
    """Poll EmailSyncCheckpoint until every mailbox is done, then
    dispatch _sync_callback. Self-reschedules on the ``sync`` queue
    rather than blocking a worker slot — see the module docstring for
    why this replaces the old chord-based hand-off.
    """
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.models.email_sync_checkpoint import (
        EmailSyncCheckpoint,
    )
    from airunner_services.database.session import session_scope

    from projects.uwuchat.server.email.sync_cancellation import (
        finish_sync,
        is_cancelled,
    )
    from projects.uwuchat.server.email.sync_progress_events import (
        emit_complete,
    )

    if is_cancelled(email_account_id):
        finish_sync(email_account_id)
        return {"status": "cancelled"}

    with tenant_scope(tenant_key):
        with session_scope() as session:
            done = (
                session.query(EmailSyncCheckpoint)
                .filter(
                    EmailSyncCheckpoint.email_account_id
                    == email_account_id,
                    EmailSyncCheckpoint.status == "completed",
                )
                .count()
            )

    # No emit_progress() here: this watchdog polls concurrently with
    # _sync_one_mailbox tasks, which own the shared current/total
    # counters via emit_progress_delta (see sync_progress_events'
    # docstring — emit_progress is only safe for phases that run
    # alone). Calling it here clobbered the message-level counter
    # with a small mailbox-count pair every poll, making the bar
    # jump past its total and reset repeatedly.

    if done >= expected_mailboxes:
        _sync_callback.apply_async(
            args=[
                expected_mailboxes, email_account_id, user_id,
                tenant_key, account_id,
            ],
            queue="sync",
        )
        return {"status": "dispatched_callback", "done": done}

    if attempt >= _MAX_POLL_ATTEMPTS:
        logger.error(
            "Mailbox sync stalled for account %d: %d/%d mailboxes "
            "completed after %d polls — giving up",
            email_account_id, done, expected_mailboxes, attempt,
        )
        emit_complete(
            email_account_id, False,
            f"Mailbox sync stalled ({done}/{expected_mailboxes} "
            "mailboxes completed)",
        )
        finish_sync(email_account_id)
        return {"status": "timeout", "done": done}

    raise self.retry(
        args=[
            email_account_id, user_id, tenant_key, account_id,
            expected_mailboxes, attempt + 1,
        ],
        kwargs={},
        countdown=_POLL_INTERVAL_SECONDS,
        max_retries=_MAX_POLL_ATTEMPTS,
    )


# -- Callback: run once every mailbox has finished ---------------------------


@app.task(
    bind=True,
    name="projects.uwuchat.server.tasks.email_tasks._sync_callback",
    queue="sync",
)
def _sync_callback(
    self,
    mailbox_count: int,
    email_account_id: int,
    user_id: int,
    tenant_key: str,
    account_id: int,
) -> dict:
    """Run delta sync + processing pipeline.

    Dispatched by ``_await_mailbox_sync`` once every per-mailbox
    child task has completed.

    After marking the account "connected", enqueues
    ``_index_email_bodies_background`` to index email bodies
    asynchronously. This decouples "connected" from "fully
    searchable" — users can connect immediately without waiting
    for embedding every thread.
    """
    import datetime

    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.models.email_account import (
        EmailAccount,
    )
    from airunner_services.database.session import session_scope
    from airunner_services.tasks.task_helpers import task_dek_scope

    from projects.uwuchat.server.email.sync_cancellation import (
        finish_sync,
        is_cancelled,
    )
    from projects.uwuchat.server.email.sync_progress_events import (
        emit_complete,
    )

    logger.info(
        "Sync callback: account=%d, %d mailboxes done",
        email_account_id, mailbox_count,
    )

    # peek=True: _sync_callback is no longer the last consumer of the
    # relay entry — it enqueues _index_email_bodies_background right
    # after completing, and that task needs to read the same entry
    # too. Consuming it here (the old default) deleted it before the
    # background indexer ever got a chance to read it, so indexing
    # silently skipped with "no_dek" on every single sync.
    with task_dek_scope(tenant_key, account_id, peek=True) as dek:
        if dek is None:
            # See the matching comment in sync_email_account: not a
            # user-facing failure, so no emit_complete here — this
            # can legitimately happen if the relay's TTL expired
            # mid-backfill on a large mailbox, and must not clobber
            # a real "sync complete" state with a false error.
            logger.info(
                "DEK relay empty in sync callback for account %d",
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
            finish_sync(email_account_id)
            return {"status": "skipped", "reason": "no_dek"}

        with tenant_scope(tenant_key):
            with session_scope() as session:
                account = session.query(EmailAccount).get(
                    email_account_id,
                )
                if account is None:
                    emit_complete(
                        email_account_id, False, "Account not found",
                    )
                    finish_sync(email_account_id)
                    return {
                        "status": "error",
                        "reason": "Account not found",
                    }
                token = account.credential_ciphertext
                if not token:
                    emit_complete(
                        email_account_id, False, "No credential",
                    )
                    finish_sync(email_account_id)
                    return {
                        "status": "error",
                        "reason": "No credential",
                    }

            from projects.uwuchat.server.email.fastmail import (
                FastmailJMAPProvider,
            )

            provider = FastmailJMAPProvider(api_token=str(token))
            mailboxes = _run_async(provider.list_mailboxes())

            try:
                from projects.uwuchat.server.email.sync_delta import (
                    delta_sync_account,
                )

                delta_sync_account(
                    email_account_id, provider, mailboxes,
                )

                # Phases 2–4: processing pipeline, in-process within
                # this Celery worker.
                from projects.uwuchat.server.email.sync_pipeline import (
                    process_new_messages,
                )

                process_new_messages(
                    email_account_id, user_id, provider,
                )

                from projects.uwuchat.server.email.stats import (
                    compute_email_stats,
                )

                compute_email_stats(email_account_id, user_id)
            except Exception as exc:
                # Anything unexpected in the processing pipeline must
                # still leave the sync in a terminal state — a bug
                # here previously left the progress bar stuck at
                # "active" forever (even across page reloads) because
                # nothing downstream of the crash ever got a chance
                # to write a completion.
                logger.error(
                    "Processing pipeline failed for account %d: %s",
                    email_account_id, exc, exc_info=True,
                )
                emit_complete(
                    email_account_id, False,
                    f"Sync partially failed: {exc}",
                )
                finish_sync(email_account_id)
                return {"status": "error", "reason": str(exc)}

            # Mark completion.
            with session_scope() as session:
                acct = session.query(EmailAccount).get(
                    email_account_id,
                )
                if acct is not None:
                    # Re-check the account's deleted/cancellation state before
                    # marking it "connected". This prevents a just-disconnected
                    # account from being resurrected as "connected" if the
                    # disconnect happened while the sync task was running.
                    if acct.deleted:
                        logger.info(
                            "Sync callback: account %d was deleted during "
                            "sync; skipping completion mark",
                            email_account_id,
                        )
                        finish_sync(email_account_id)
                        return {
                            "status": "cancelled",
                            "reason": "account_deleted_during_sync",
                        }

                    if is_cancelled(email_account_id):
                        logger.info(
                            "Sync callback: account %d was cancelled during "
                            "sync; skipping completion mark",
                            email_account_id,
                        )
                        finish_sync(email_account_id)
                        return {
                            "status": "cancelled",
                            "reason": "sync_cancelled_during_sync",
                        }

                    acct.last_synced_at = (
                        datetime.datetime.utcnow()
                    )
                    acct.backfill_completed_at = (
                        datetime.datetime.utcnow()
                    )
                    acct.status = "connected"
                    acct.error_message = None
                    session.commit()

            # Enqueue background indexing task after marking completion.
            # This decouples "connected" from "fully searchable".
            from projects.uwuchat.server.tasks.email_indexing_tasks import (
                _index_email_bodies_background,
            )

            _index_email_bodies_background.apply_async(
                args=[
                    email_account_id, user_id, tenant_key, account_id,
                ],
                queue="sync",
            )

    emit_complete(email_account_id, True, "Email sync complete")
    finish_sync(email_account_id)
    logger.info(
        "Sync complete for account %d", email_account_id,
    )
    return {
        "status": "complete",
        "account_id": email_account_id,
        "mailbox_results": mailbox_count,
    }


# -- Helpers ----------------------------------------------------------------


def _run_async(coro):
    """Run an async coroutine in a sync context (Celery task)."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _update_checkpoint(
    account_id: int,
    mailbox_id: str,
    position: int,
    processed: int,
) -> None:
    """Persist the latest backfill cursor position."""
    from airunner_services.database.models.email_sync_checkpoint import (
        EmailSyncCheckpoint,
    )
    from airunner_services.database.session import session_scope

    with session_scope() as session:
        row = (
            session.query(EmailSyncCheckpoint)
            .filter(
                EmailSyncCheckpoint.email_account_id == account_id,
                EmailSyncCheckpoint.mailbox_id == mailbox_id,
            )
            .first()
        )
        if row is not None:
            row.last_position = position
            row.emails_processed = processed


def _mark_checkpoint_complete(
    account_id: int,
    mailbox_id: str,
    processed: int,
) -> None:
    """Mark a mailbox checkpoint as completed."""
    from airunner_services.database.models.email_sync_checkpoint import (
        EmailSyncCheckpoint,
    )
    from airunner_services.database.session import session_scope

    with session_scope() as session:
        row = (
            session.query(EmailSyncCheckpoint)
            .filter(
                EmailSyncCheckpoint.email_account_id == account_id,
                EmailSyncCheckpoint.mailbox_id == mailbox_id,
            )
            .first()
        )
        if row is not None:
            row.last_position = row.last_position or 0
            row.status = "completed"
            row.emails_processed = processed
            session.commit()
