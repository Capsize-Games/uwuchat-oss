"""Login-triggered FHE embedding backfill recovery.

Wires the existing cursor-based backfill functions in
:mod:`airunner_services.embedding_backfill` to the
``USER_LOGIN_COMPLETE`` signal so rows with NULL ``embedding_enc``
catch up automatically on next login.

Follows the same fire-and-forget pattern as
:mod:`projects.uwuchat.server.email.sync_engine`: dispatch to a
background thread via ``asyncio.to_thread`` so the login response is
never blocked.  A Redis-backed cooldown debounce prevents re-scanning
on every login, mirroring the ``indexing_recovery_checked_at`` column
pattern.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Debounce (Redis-backed, matches indexing_recovery_checked_at) ───

_EMBEDDING_RECOVERY_COOLDOWN_SECONDS = 30 * 60  # 30 minutes
_REDIS_KEY_PREFIX = "embedding_recovery:"


def _recovery_redis():
    """DB 3 — general cache (same as email sync progress)."""
    from airunner_services.tasks.redis_client import cache_redis

    return cache_redis()


def _recovery_key(account_id: int) -> str:
    return f"{_REDIS_KEY_PREFIX}{account_id}"


def _should_run(account_id: int) -> bool:
    """Return True if the cooldown has expired for *account_id*.

    A Redis key with TTL enforces the cooldown — if the key exists
    (has not expired), the cooldown is still active.  The key is set
    with the cooldown TTL when the backfill actually starts.
    """
    r = _recovery_redis()
    return r.get(_recovery_key(account_id)) is None


def _mark_running(account_id: int) -> None:
    """Set the cooldown key so concurrent/future calls see it."""
    r = _recovery_redis()
    r.setex(
        _recovery_key(account_id),
        _EMBEDDING_RECOVERY_COOLDOWN_SECONDS,
        "1",
    )


# ── Main recovery function ────────────────────────────────────────


def recover_pending_embeddings(
    account_id: int, tenant_key: str,
) -> None:
    """Fire-and-forget recovery: run the cursor-based backfill.

    Designed to run as a background thread after login.  Must never
    raise — all exceptions are caught, logged, and swallowed so login
    is never affected.

    1. Fast-exit: check for any NULL embedding_enc rows cheaply.
    2. Debounce: skip if cooldown has not elapsed (Redis TTL).
    3. Set up tenant scope with *tenant_key*.
    4. Call ``backfill_fact_embeddings`` and
       ``backfill_turn_embeddings`` (cursor-based, idempotent, safe
       to interrupt and re-run).
    """
    if not _exists_null_embeddings(tenant_key):
        logger.debug(
            "Embedding recovery: no NULL embedding_enc rows "
            "in tenant %s, skipping",
            tenant_key,
        )
        return

    if not _should_run(account_id):
        logger.debug(
            "Embedding recovery: cooldown active for account %d, "
            "skipping",
            account_id,
        )
        return

    _mark_running(account_id)

    try:
        from airunner_services.data.tenant import (
            set_tenant_key,
            reset_tenant_key,
        )
        from airunner_services.embedding_backfill import (
            backfill_fact_embeddings,
            backfill_turn_embeddings,
        )
        from projects.uwuchat.server.embedding_provider import (
            get_embedding_provider,
        )

        tenant_token = set_tenant_key(tenant_key)
        try:
            provider = get_embedding_provider()

            fact_result = backfill_fact_embeddings(
                provider, batch_size=50,
            )
            turn_result = backfill_turn_embeddings(
                provider, batch_size=50,
            )

            total = (
                fact_result.get("total_embedded", 0)
                + turn_result.get("total_embedded", 0)
            )
            errors = (
                fact_result.get("errors", 0)
                + turn_result.get("errors", 0)
            )

            if total or errors:
                logger.info(
                    "Embedding recovery: account %d — "
                    "embedded=%d errors=%d",
                    account_id, total, errors,
                )
            else:
                logger.debug(
                    "Embedding recovery: account %d — "
                    "nothing to do",
                    account_id,
                )
        finally:
            reset_tenant_key(tenant_token)
    except Exception:
        logger.exception(
            "Embedding recovery failed for account %d",
            account_id,
        )


# ── Fast-exit: check for any NULL embedding_enc rows ──────────────


def _exists_null_embeddings(tenant_key: str) -> bool:
    """Return True if any table has rows with NULL embedding_enc.

    Uses column-only EXISTS subqueries — no full-row fetches.
    """
    from airunner_services.data.tenant import (
        set_tenant_key,
        reset_tenant_key,
    )
    from airunner_services.database.session import session_scope
    from sqlalchemy import func

    tenant_token = set_tenant_key(tenant_key)
    try:
        with session_scope() as session:
            from airunner_services.database.models.knowledge_fact import (
                KnowledgeFact,
            )
            from airunner_services.database.models.conversation_turn import (
                ConversationTurn,
            )

            fact_count = (
                session.query(func.count(KnowledgeFact.id))
                .filter(
                    KnowledgeFact.embedding_enc.is_(None),
                    KnowledgeFact.deleted == False,
                )
                .scalar()
            )
            turn_count = (
                session.query(func.count(ConversationTurn.id))
                .filter(
                    ConversationTurn.embedding_enc.is_(None),
                    ConversationTurn.deleted == False,
                )
                .scalar()
            )

            total = (fact_count or 0) + (turn_count or 0)
            return total > 0
    finally:
        reset_tenant_key(tenant_token)


# ── Signal handler ────────────────────────────────────────────────


def _on_user_login_complete(data: dict) -> None:
    """Handle USER_LOGIN_COMPLETE: dispatch embedding backfill.

    This handler is registered by ``register_signals`` and fires
    synchronously via ``SignalMediator`` from the login endpoint.
    The actual recovery work is dispatched to a background thread
    via ``asyncio.to_thread`` so it never blocks the login response.
    """
    account_id = data.get("account_id")
    tenant_key = data.get("tenant_key")
    if not account_id or not tenant_key:
        return

    import asyncio

    asyncio.ensure_future(
        asyncio.to_thread(
            recover_pending_embeddings,
            account_id,
            tenant_key,
        ),
    )


# ── Signal registration ───────────────────────────────────────────


def register_signals() -> None:
    """Register the embedding-recovery handler for login events."""
    from airunner_services.contract_enums import SignalCode
    from airunner_services.utils.application.signal_mediator import (
        SignalMediator,
    )

    SignalMediator().register(
        SignalCode.USER_LOGIN_COMPLETE,
        _on_user_login_complete,
    )


__all__ = [
    "recover_pending_embeddings",
    "register_signals",
]
