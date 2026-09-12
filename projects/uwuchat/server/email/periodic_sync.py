"""Periodic email sync scheduler — iterates all tenants and triggers
EMAIL_START_SYNC for connected accounts.

Follows the same asyncio-loop-from-lifespan pattern as
``hardware_broadcast.py``.  No new scheduling dependency.
"""

from __future__ import annotations

import asyncio
import logging
import os

from airunner_services.contract_enums import SignalCode
from sqlalchemy import text

from airunner_services.database.models.email_account import EmailAccount
from airunner_services.database.session import (
    public_session_scope,
    session_scope,
)
from airunner_services.data.tenant import (
    tenant_scope,
    tenant_key_from_schema,
)

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_HOURS = int(
    os.environ.get("EMAIL_SYNC_INTERVAL_HOURS", "4"),
)


def start_periodic_email_sync() -> asyncio.Task:
    """Start an asyncio loop that periodically triggers email syncs.

    Follows the exact same shape as
    ``start_hardware_broadcast()`` — a plain synchronous function
    returning ``asyncio.create_task(_loop())``.
    """
    async def _loop() -> None:
        while True:
            try:
                await _trigger_all_connected()
            except Exception as exc:
                logger.error(
                    "Periodic email sync tick failed: %s", exc,
                )
            await asyncio.sleep(_DEFAULT_INTERVAL_HOURS * 3600)

    return asyncio.create_task(_loop())


async def _trigger_all_connected() -> None:
    """Find every tenant schema, enter its scope, and emit
    EMAIL_START_SYNC for each connected EmailAccount."""
    from airunner_services.utils.application.signal_mediator import (
        SignalMediator,
    )

    schemas = _list_tenant_schemas()
    if not schemas:
        return

    mediator = SignalMediator()
    triggered = 0
    for schema in schemas:
        tenant_key = tenant_key_from_schema(schema)
        if not tenant_key:
            continue
        try:
            with tenant_scope(tenant_key):
                with session_scope() as session:
                    # Column-only: this loop runs with no DEK active
                    # by design, and EmailAccount.credential_ciphertext
                    # is decrypted eagerly on row-fetch — loading full
                    # entities here would raise DataEncryptionError
                    # for every account and silently abort this whole
                    # tenant's periodic trigger every single tick.
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
                        from airunner_services.data.tenant import (
                            account_id_scope,
                        )

                        # Enter account_id_scope so the signal handler
                        # can resolve the account ID via get_account_id()
                        # rather than only via the data dict (which the
                        # handler uses as a fallback when the ContextVar
                        # is empty).
                        with account_id_scope(acct_user_id):
                            mediator.emit_signal(
                                SignalCode.EMAIL_START_SYNC,
                                {"email_account_id": acct_id},
                            )
                        triggered += 1
        except Exception as exc:
            logger.warning(
                "Skipping tenant %s: %s", tenant_key, exc,
            )
    logger.info(
        "Periodic email sync: triggered %d accounts", triggered,
    )


def _list_tenant_schemas() -> list[str]:
    """Return all tenant schema names from the public database."""
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
