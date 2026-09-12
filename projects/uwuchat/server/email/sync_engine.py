"""Sync engine entry point — signal handler that enqueues the Celery
sync task.

Receives ``EMAIL_START_SYNC``, captures the tenant key + DEK, and
hands off to Celery (``projects.uwuchat.server.tasks.email_tasks``).
All per-mailbox logic lives in that module and
``sync_backfill.py``/``sync_delta.py``; phase 2-4 processing lives in
``sync_pipeline.py``.
"""

from __future__ import annotations

import logging

from airunner_services.contract_enums import SignalCode
from airunner_services.utils.application.signal_mediator import (
    SignalMediator,
)
from airunner_services.utils.crypto.dek_cache import get_user_dek

from .sync_cancellation import start_sync
from .sync_progress_store import email_sync_progress_start

logger = logging.getLogger(__name__)


# ---- Signal handler -------------------------------------------------------


def on_email_start_sync_signal(data: dict) -> None:
    """Enqueue a Celery task to sync one email account.

    Captures the tenant key, account_id, and DEK before enqueuing.
    The DEK is written to the relay (Redis DB 2) so the Celery
    worker can read it on start.  Does NOT spawn a raw thread —
    Celery handles the lifecycle.

    ``account_id`` is first read from the ContextVar (set by the HTTP
    auth middleware or ``account_id_scope``), falling back to the
    ``"account_id"`` key in the signal data dict (used when emitting
    from a thread-pool context).  If neither source yields a value,
    the function returns early — there is no way to proceed safely
    without knowing who the platform account is.

    When no live DEK is available (e.g. periodic Beat trigger), the
    relay write is skipped but the sync task is still enqueued
    (the Celery worker follows the Tier-2 skip-and-defer path when
    the relay entry is absent).  The pending-indexing retry is
    called regardless — it only enqueues Celery tasks, so it does
    not need a live DEK itself.
    """
    from airunner_services.data.tenant import get_account_id, get_tenant_key

    email_account_id = int((data or {}).get("email_account_id", 0))
    if not email_account_id:
        logger.warning(
            "EMAIL_START_SYNC called with no email_account_id",
        )
        return

    tenant_key = get_tenant_key()
    account_id = get_account_id()
    user_dek = get_user_dek()

    # Fallback: use the account_id from the signal data when the
    # ContextVar is empty (e.g. emission from a thread-pool worker
    # where ContextVars may not propagate, or from a context that
    # only set tenant_scope but not account_id_scope).
    if account_id is None:
        account_id = (data or {}).get("account_id")

    if account_id is None:
        logger.warning(
            "EMAIL_START_SYNC: no account_id available in context "
            "or data dict — cannot enqueue sync task for account %d",
            email_account_id,
        )
        return

    logger.info(
        "Enqueuing email sync for account %s (tenant=%s, user=%d)",
        email_account_id, tenant_key, account_id,
    )

    start_sync(email_account_id)
    email_sync_progress_start(email_account_id)

    # Write DEK to relay so the Celery worker can pick it up.
    # The live DEK is only available during an authenticated session
    # (HTTP auth middleware or ws_dek_scope); when absent (periodic
    # Beat trigger), skip the relay write but still enqueue the task
    # so the Celery worker can follow skip-and-defer.
    if user_dek is not None:
        from airunner_services.tasks.task_helpers import (
            wrap_dek_for_relay,
        )
        from airunner_services.tasks.redis_client import (
            dek_relay_store,
        )

        wrapped = wrap_dek_for_relay(user_dek)
        dek_relay_store(account_id, wrapped)

    # Enqueue the Celery task.
    from projects.uwuchat.server.tasks.email_tasks import (
        sync_email_account,
    )

    sync_email_account.apply_async(
        args=[email_account_id, tenant_key, account_id],
        queue="sync",
        task_id=f"email-sync-{email_account_id}",
    )

    # Retry background indexing for any accounts that have
    # ``indexing_status = "pending"``.  This fires regardless of
    # whether a live DEK is available:
    #
    # - When a live DEK IS available (connect path), the relay entry
    #   was just written above, so ``_index_email_bodies_background``
    #   can consume it and indexing succeeds.
    # - When no DEK is available (periodic Beat trigger), the retried
    #   background tasks will follow skip-and-defer (marking pending
    #   again), which is harmless — the next connect-path retry
    #   eventually catches up.
    _retry_pending_indexing(tenant_key, account_id)


# ---- Pending-indexing retry helper -----------------------------------------


def _retry_pending_indexing(tenant_key: str, account_id: int) -> None:
    """Re-enqueue background indexing for accounts with ``indexing_status = "pending"``.

    Called after a fresh DEK relay entry has been written (during an
    authenticated session with a live DEK). Queries the current tenant
    schema for accounts whose background indexing was skipped due to a
    missing DEK, and enqueues ``_index_email_bodies_background`` for
    each.
    """
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.models.email_account import (
        EmailAccount,
    )
    from airunner_services.database.session import session_scope
    from projects.uwuchat.server.tasks.email_indexing_tasks import (
        _index_email_bodies_background,
    )

    with tenant_scope(tenant_key):
        with session_scope() as session:
            # Column-only: this can run with no DEK active (e.g. the
            # periodic-sync path), and EmailAccount.credential_ciphertext
            # is decrypted eagerly on row-fetch — loading the full
            # entity here would raise DataEncryptionError instead of
            # just enqueueing the retry.
            pending = (
                session.query(EmailAccount.id, EmailAccount.user_id)
                .filter(
                    EmailAccount.indexing_status == "pending",
                    EmailAccount.deleted == False,
                )
                .all()
            )
        if not pending:
            return

        for acct_id, acct_user_id in pending:
            logger.info(
                "Retrying pending background indexing for account %d "
                "(tenant=%s)",
                acct_id, tenant_key,
            )
            _index_email_bodies_background.apply_async(
                args=[
                    acct_id, acct_user_id, tenant_key, account_id,
                ],
                queue="sync",
            )


# ---- Login-recovery hook ---------------------------------------------------

_INDEXING_RECOVERY_COOLDOWN_MINUTES = 30


def recover_pending_email_indexing(account_id: int, password: str) -> None:
    """Fire-and-forget recovery: re-derive DEK, write to relay, retry
    pending indexing.

    Designed to run as a background thread after login (mirroring
    ``_backfill_user_encryption``).  Must never raise — all exceptions
    are caught, logged, and swallowed so login is never affected.

    1. Look up the account's ``tenant_schema``, ``wrapped_dek``,
       ``dek_kdf_salt``, ``dek_kdf_params`` in the public schema,
       capturing everything before the session closes.
    2. Fast-exit: if the user's tenant has **zero** ``EmailAccount``
       rows, return immediately — no-op for users who have never
       connected email. Column-only aggregate, no DEK required, so
       this stays cheap and runs before the KDF derivation below.
    3. Re-derive the DEK from the captured envelope + password. This
       must happen before any full ``EmailAccount`` row is loaded —
       that model has a ``UserEncryptedText`` column
       (``credential_ciphertext``) that gets decrypted eagerly on
       row-fetch by SQLAlchemy, so every full-entity query below
       needs an active ``dek_scope`` or it fails with
       ``DataEncryptionError``.
    4. Debounce: skip accounts whose ``indexing_recovery_checked_at``
       is within the cooldown window (30 minutes). Column-only query
       + bulk update — avoids holding ORM entities across a session
       boundary (which would raise ``DetachedInstanceError`` once
       expired on commit).
    5. Reconcile legacy (``indexing_status IS NULL``) accounts:
       compare distinct thread counts between ``EmailMessage`` and
       ``EmailBodyChunk`` for this tenant.
    6. Write the DEK into the relay (``wrap_dek_for_relay`` +
       ``dek_relay_store``).
    7. Call ``_retry_pending_indexing`` for whatever is still
       ``"pending"`` after the reconciliation step.
    """
    import logging as _logging

    _log = _logging.getLogger("airunner.email.indexing_recovery")

    try:
        from airunner_services.database.session import (
            public_session_scope,
        )
        from extensions.auth.server.models import Account

        # Step 1: Capture envelope fields from public schema.
        with public_session_scope() as pub_session:
            account = (
                pub_session.query(Account)
                .filter(Account.id == account_id)
                .first()
            )
            if account is None or account.wrapped_dek is None:
                _log.warning(
                    "Indexing recovery skipped for account %d: "
                    "no envelope",
                    account_id,
                )
                return
            tenant_schema = account.tenant_schema
            dek_kdf_salt = account.dek_kdf_salt
            dek_kdf_params = account.dek_kdf_params
            wrapped_dek = account.wrapped_dek

        from airunner_services.data.tenant import (
            tenant_key_from_schema,
        )

        tenant_key = tenant_key_from_schema(tenant_schema)

        from airunner_services.data.tenant import (
            set_tenant_key,
            reset_tenant_key,
        )
        from airunner_services.utils.crypto.dek_cache import (
            dek_scope,
        )
        from airunner_services.database.session import (
            session_scope,
        )
        from airunner_services.database.models.email_account import (
            EmailAccount,
        )
        from airunner_services.database.models.email_message import (
            EmailMessage,
        )
        from airunner_services.database.models.email_body_chunk import (
            EmailBodyChunk,
        )
        from sqlalchemy import func

        tenant_token = set_tenant_key(tenant_key)
        try:
            # Step 2: Fast exit — no EmailAccount rows at all. This
            # is a column-only aggregate (no credential_ciphertext
            # in the SELECT), so it needs no DEK and runs before the
            # (comparatively expensive) KDF derivation below — most
            # logins are for users who've never connected email, and
            # this must stay cheap for them.
            with session_scope() as session:
                account_count = (
                    session.query(func.count(EmailAccount.id))
                    .filter(EmailAccount.deleted == False)
                    .scalar()
                )
                if account_count == 0:
                    _log.debug(
                        "Indexing recovery: no EmailAccount rows "
                        "in tenant %s, skipping",
                        tenant_key,
                    )
                    return

            # Step 3: Re-derive the DEK from the captured envelope +
            # password *before* touching any full EmailAccount row —
            # that model's credential_ciphertext column is
            # UserEncryptedText and gets decrypted eagerly on
            # row-fetch, so every full-entity query below needs an
            # active dek_scope, not just the relay write at the end.
            from airunner_services.utils.crypto.user_envelope import (
                decode_salt,
                derive_kek,
                unwrap_dek,
            )

            salt = decode_salt(dek_kdf_salt)
            kek = derive_kek(password, salt, params=dek_kdf_params)
            dek = unwrap_dek(wrapped_dek, kek)

            with dek_scope(dek):
                # Step 4: Debounce — check cooldown for all accounts.
                # Column-only: (a) avoids ever touching
                # credential_ciphertext for accounts that don't need
                # reconciliation, and (b) avoids holding ORM entities
                # across a session boundary — with the default
                # expire_on_commit=True, those would raise
                # DetachedInstanceError the moment they're touched
                # again after the session that loaded them closes.
                import datetime

                now = datetime.datetime.utcnow()
                cooldown_cutoff = now - datetime.timedelta(
                    minutes=_INDEXING_RECOVERY_COOLDOWN_MINUTES,
                )

                with session_scope() as session:
                    accounts_to_process = (
                        session.query(
                            EmailAccount.id,
                            EmailAccount.indexing_status,
                        )
                        .filter(
                            (
                                EmailAccount
                                .indexing_recovery_checked_at
                                .is_(None)
                            )
                            | (
                                EmailAccount
                                .indexing_recovery_checked_at
                                < cooldown_cutoff
                            ),
                            EmailAccount.deleted == False,
                        )
                        .all()
                    )

                    if not accounts_to_process:
                        _log.debug(
                            "Indexing recovery: all %d EmailAccount "
                            "rows recently checked, skipping "
                            "(tenant=%s)",
                            account_count, tenant_key,
                        )
                        return

                    # Mark all as checked now (before doing work) so
                    # a concurrent call from a parallel login doesn't
                    # also process them.
                    account_ids = [
                        acct_id for acct_id, _ in accounts_to_process
                    ]
                    session.query(EmailAccount).filter(
                        EmailAccount.id.in_(account_ids),
                    ).update(
                        {"indexing_recovery_checked_at": now},
                        synchronize_session=False,
                    )
                    session.commit()

                # Step 5: Reconcile legacy NULL indexing_status
                # accounts.
                for acct_id, indexing_status in accounts_to_process:
                    if indexing_status is not None:
                        continue

                    with session_scope() as session:
                        # Count distinct thread_ids in EmailMessage.
                        msg_thread_count = (
                            session.query(func.count(
                                func.distinct(EmailMessage.thread_id),
                            ))
                            .filter(
                                EmailMessage.email_account_id
                                == acct_id,
                                EmailMessage.deleted == False,
                            )
                            .scalar()
                            or 0
                        )

                        # Count distinct thread_ids in
                        # EmailBodyChunk. Must filter out
                        # soft-deleted chunks so a thread whose
                        # chunks were deleted doesn't count toward
                        # "indexed" — matching the filter used by
                        # search_email_body_chunks in email_rag.py.
                        chunk_thread_count = (
                            session.query(func.count(
                                func.distinct(
                                    EmailBodyChunk.thread_id,
                                ),
                            ))
                            .filter(
                                EmailBodyChunk.email_account_id
                                == acct_id,
                                EmailBodyChunk.deleted == False,
                            )
                            .scalar()
                            or 0
                        )

                        # If chunks cover materially fewer threads,
                        # mark as pending so background indexing
                        # picks them up. "Materially fewer" means
                        # < 90% coverage, with a small fudge factor
                        # for the common case where a
                        # newly-connected account has zero chunks.
                        if (
                            msg_thread_count > 0
                            and chunk_thread_count
                            < msg_thread_count * 0.9
                        ):
                            update_fields = {
                                "indexing_status": "pending",
                                "indexing_recovery_checked_at": now,
                            }
                            _log.info(
                                "Reclassified account %d as pending "
                                "(messages=%d threads, chunks=%d "
                                "threads)",
                                acct_id, msg_thread_count,
                                chunk_thread_count,
                            )
                        else:
                            update_fields = {
                                "indexing_status": "complete",
                            }
                            _log.info(
                                "Reclassified account %d as "
                                "complete (messages=%d threads, "
                                "chunks=%d threads)",
                                acct_id, msg_thread_count,
                                chunk_thread_count,
                            )
                        session.query(EmailAccount).filter(
                            EmailAccount.id == acct_id,
                        ).update(
                            update_fields, synchronize_session=False,
                        )
                        session.commit()

                # Step 6: Write DEK to relay.
                from airunner_services.tasks.task_helpers import (
                    wrap_dek_for_relay,
                )
                from airunner_services.tasks.redis_client import (
                    dek_relay_store,
                )

                wrapped = wrap_dek_for_relay(dek)
                dek_relay_store(account_id, wrapped)

                # Step 7: Retry pending indexing.
                _retry_pending_indexing(tenant_key, account_id)

                _log.info(
                    "Indexing recovery complete for account %d",
                    account_id,
                )
        finally:
            reset_tenant_key(tenant_token)
    except Exception:
        _log.exception(
            "Indexing recovery failed for account %d",
            account_id,
        )


# ---- Login-recovery signal handler -----------------------------------------


def _on_user_login_complete(data: dict) -> None:
    """Handle USER_LOGIN_COMPLETE: dispatch pending-indexing recovery.

    This handler is registered by ``register_signals`` and fires
    synchronously via ``SignalMediator`` from the login endpoint.
    The actual recovery work is dispatched to a background thread
    via ``asyncio.to_thread`` so it never blocks the login response.
    """
    account_id = data.get("account_id")
    password = data.get("password", "")
    if not account_id:
        return

    import asyncio

    asyncio.ensure_future(
        asyncio.to_thread(
            recover_pending_email_indexing,
            account_id,
            password,
        ),
    )


# ---- Signal registration --------------------------------------------------


def register_signals() -> None:
    """Register the email-sync handler and login-recovery handler."""
    SignalMediator().register(
        SignalCode.EMAIL_START_SYNC,
        on_email_start_sync_signal,
    )
    SignalMediator().register(
        SignalCode.USER_LOGIN_COMPLETE,
        _on_user_login_complete,
    )
