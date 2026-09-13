"""Celery Beat periodic tasks — replaces ``periodic_sync.py``'s
asyncio loop with Celery Beat scheduling.

The periodic trigger does NOT perform email sync directly —
it only enumerates connected accounts and enqueues per-account
sync tasks onto the ``sync`` queue.  This keeps the Beat
process lightweight and makes each per-tenant sync individually
visible and retriable.
"""

from __future__ import annotations

import os
from datetime import timedelta

from airunner_services.tasks.celery_app import app
from celery.schedules import crontab
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

# Crontab expressions — must remain strings, not integers.
_EMAIL_SYNC_MINUTE = os.environ.get("EMAIL_SYNC_MINUTE", "0")
_EMAIL_SYNC_HOUR = os.environ.get("EMAIL_SYNC_HOUR", "*/4")

# Poll cadence for running headlesscode sessions — conservative start,
# tune after real usage (the plan doc's Phase 4 recommendation).
_HEADLESSCODE_POLL_SECONDS = float(
    os.environ.get("HEADLESSCODE_POLL_SECONDS", "2")
)

# Exported so celery_app.py can import and merge into beat_schedule.
PERIODIC_EMAIL_SYNC_SCHEDULE = {
    "trigger-email-sync-all-tenants": {
        "task": (
            "projects.uwuchat.server.tasks"
            ".periodic_tasks.trigger_all_connected"
        ),
        "schedule": crontab(
            minute=_EMAIL_SYNC_MINUTE,
            hour=_EMAIL_SYNC_HOUR,
        ),
        "options": {"queue": "sync"},
    },
}

# Headlesscode Phase 4: the Beat trigger stays lightweight — it only
# enumerates running sessions and enqueues one poll task per session
# (see headlesscode_poll_tasks), so per-session failures stay isolated
# and individually visible.
PERIODIC_HEADLESSCODE_POLL_SCHEDULE = {
    "poll-headlesscode-running-sessions": {
        "task": (
            "projects.uwuchat.server.tasks.headlesscode_poll_tasks."
            "trigger_headlesscode_session_polling"
        ),
        "schedule": timedelta(seconds=_HEADLESSCODE_POLL_SECONDS),
        "options": {"queue": "sync"},
    },
}


@app.task(
    bind=True,
    name=(
        "projects.uwuchat.server.tasks"
        ".periodic_tasks.trigger_all_connected"
    ),
    max_retries=2,
    default_retry_delay=300,  # 5 min between retries
)
def trigger_all_connected(self) -> dict:
    """Find every tenant schema and enqueue a per-account sync task.

    This task runs unattended (no live user session), so it follows
    the Tier-2 skip-and-defer path: accounts without a relayed DEK
    are skipped (logged) rather than attempted with a missing DEK.
    The next live session for that account will trigger a catch-up
    sync (see ``sync_engine.py``'s on-connect hook).
    """
    from airunner_services.data.tenant import (
        tenant_key_from_schema,
        tenant_scope,
    )
    from airunner_services.database.models.email_account import (
        EmailAccount,
    )
    from airunner_services.database.session import (
        session_scope,
    )

    # List tenant schemas from the public schema.
    schemas = _list_tenant_schemas()
    if not schemas:
        logger.info("Periodic email sync: no tenant schemas found")
        return {"enqueued": 0, "skipped": 0}

    enqueued = 0
    skipped = 0

    for schema in schemas:
        tenant_key = tenant_key_from_schema(schema)
        if not tenant_key:
            continue
        try:
            with tenant_scope(tenant_key):
                with session_scope() as session:
                    # Column-only: this task has NO live DEK by
                    # design, and EmailAccount.credential_ciphertext
                    # is decrypted eagerly on row-fetch — loading full
                    # entities here would raise DataEncryptionError
                    # for every account and abort this whole tenant's
                    # periodic trigger every single tick instead of
                    # cleanly enqueueing the skip-and-defer task.
                    accounts = (
                        session.query(
                            EmailAccount.id, EmailAccount.user_id,
                        )
                        .filter(
                            EmailAccount.status == "connected",
                            EmailAccount.deleted == False,
                        )
                        .all()
                    )
                    for acct_id, acct_user_id in accounts:
                        # Tier 2 task — enqueue from the periodic
                        # trigger which has NO live DEK.  The worker
                        # will attempt the relay read; on empty relay
                        # it follows skip-and-defer.
                        _enqueue_sync_task(
                            acct_id,
                            tenant_key,
                            acct_user_id,
                        )
                        enqueued += 1
        except Exception as exc:
            logger.warning(
                "Skipping tenant %s: %s", tenant_key, exc,
            )
            skipped += 1

    logger.info(
        "Periodic email sync: enqueued %d, skipped %d tenants",
        enqueued,
        skipped,
    )
    return {"enqueued": enqueued, "skipped": skipped}


# -- Helpers ----------------------------------------------------------------


def _enqueue_sync_task(
    email_account_id: int,
    tenant_key: str,
    account_id: int,
) -> None:
    """Enqueue a per-account email sync task onto the sync queue.

    All three args are passed explicitly — contextvars do not cross
    the Celery broker boundary.
    """
    from .email_tasks import sync_email_account

    sync_email_account.apply_async(
        args=[email_account_id, tenant_key, account_id],
        queue="sync",
        task_id=f"email-sync-{email_account_id}",
    )


def _list_tenant_schemas() -> list[str]:
    """Return all tenant schema names from the public database."""
    from airunner_services.database.session import public_session_scope
    from sqlalchemy import text

    try:
        with public_session_scope() as session:
            result = session.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name LIKE 'tenant_%'",
                ),
            )
            return [row[0] for row in result.fetchall()]
    except Exception as exc:
        logger.warning("Failed to list tenant schemas: %s", exc)
        return []
