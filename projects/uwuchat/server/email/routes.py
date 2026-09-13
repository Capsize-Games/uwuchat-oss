"""Email account linking / unlinking routes (Phase 0).

Endpoints:
  POST /connect/{user_id}     — link a Fastmail account
  POST /disconnect/{user_id}  — unlink + cascade-delete all derived data
  GET  /status/{user_id}      — connection status
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from airunner_services.contract_enums import SignalCode
from airunner_services.database.models.email_account import EmailAccount
from airunner_services.database.session import session_scope
from airunner_services.utils.application.signal_mediator import (
    SignalMediator,
)
from extensions.auth.server.dependencies import require_auth

from ._route_helpers import cascade_delete_email_data, validate_fastmail_token

logger = logging.getLogger(__name__)

router = APIRouter()

# Linking a new Fastmail account is temporarily disabled — see
# plans/uwuchat-embedding-rate-limit-priority-lanes.md and
# https://github.com/<your-org>/airunnerweb/issues/23. The email
# feature's embedding pipeline shares one account-wide provider key
# across every customer with no distributed rate limiting yet; a
# single mailbox backfill was enough to saturate it. Existing
# connections and their data are untouched — only *new* connections
# are blocked, at both the HTTP and WS-RPC entry points, until the
# rate limiter in that plan is implemented and verified.
EMAIL_CONNECT_DISABLED = True
EMAIL_CONNECT_DISABLED_MESSAGE = (
    "Email linking is temporarily unavailable while we improve "
    "how it scales. Please check back soon."
)

# WS-RPC handlers (connect/status/disconnect) live in rpc_routes.py;
# importing by name (not binding it) registers their _rpc_register
# decorators at startup without an unused-import warning.
importlib.import_module(f"{__package__}.rpc_routes")


# ---- Shared helpers (used by both HTTP and RPC handlers) ------------------


def _do_connect(
    user_id: int,
    token: str,
    email_address: str,
) -> tuple[int, dict]:
    """Upsert an EmailAccount row and return (account_id, response_dict).

    Reactivates a soft-deleted row for the same user+address when one
    exists, so ``email_accounts`` does not accumulate duplicate rows
    across disconnect/reconnect cycles.
    """
    with session_scope() as session:
        # Column-only existence check: avoids loading the full entity
        # (and thus eagerly decrypting the old credential_ciphertext,
        # which requires an active DEK and isn't needed here — we're
        # about to overwrite it, not read it).
        existing_id = (
            session.query(EmailAccount.id)
            .filter(
                EmailAccount.user_id == user_id,
                EmailAccount.email_address == email_address,
            )
            .scalar()
        )
        if existing_id is not None:
            session.query(EmailAccount).filter(
                EmailAccount.id == existing_id,
            ).update(
                {
                    "credential_ciphertext": token,
                    "status": "connected",
                    "error_message": None,
                    "deleted": False,
                },
                synchronize_session=False,
            )
            account_id = existing_id
        else:
            acct = EmailAccount(
                user_id=user_id,
                provider="fastmail",
                email_address=email_address,
                credential_ciphertext=token,
            )
            session.add(acct)
            session.flush()
            account_id = acct.id
        session.commit()

    # Fire-and-forget the sync signal so the backfill starts
    # immediately after account linking. Pass account_id explicitly
    # in the data dict since ContextVars don't cross the thread-pool
    # boundary (asyncio.to_thread in the HTTP handler).
    try:
        SignalMediator().emit_signal(
            SignalCode.EMAIL_START_SYNC,
            {
                "email_account_id": account_id,
                "account_id": user_id,
            },
        )
    except Exception:
        logger.warning("Failed to emit EMAIL_START_SYNC", exc_info=True)

    return account_id, {
        "connected": True,
        "provider": "fastmail",
        "email_address": email_address,
    }


def _do_status(user_id: int) -> dict:
    """Return the email connection status dict for one user.

    Column-only query: none of the fields returned here need
    ``credential_ciphertext``, and loading the full entity would
    eagerly decrypt that column (requiring an active DEK this
    read-only status check has no reason to depend on).
    """
    with session_scope() as session:
        row = (
            session.query(
                EmailAccount.status,
                EmailAccount.email_address,
                EmailAccount.provider,
                EmailAccount.last_synced_at,
                EmailAccount.error_message,
            )
            .filter(
                EmailAccount.user_id == user_id,
                EmailAccount.deleted == False,
            )
            .first()
        )
        if row is None:
            return {
                "connected": False,
                "status": "not_connected",
                "email_address": None,
                "provider": None,
                "last_synced_at": None,
                "error": None,
            }
        status, email_address, provider, last_synced_at, error = row
        return {
            "connected": True,
            "status": status,
            "email_address": email_address,
            "provider": provider,
            "last_synced_at": (
                last_synced_at.isoformat() if last_synced_at else None
            ),
            "error": error,
        }


def _do_sync_progress(user_id: int) -> dict:
    """Return the live sync-progress state for one user's account.

    Reads the cross-process Redis store (see ``sync_progress_store``)
    that the Celery sync tasks write to — this is the only reliable
    way to observe progress once sync moved off the API server's own
    process. Returns the idle shape when there is no linked account.
    """
    from .sync_progress_store import email_sync_progress_read

    with session_scope() as session:
        # Column-only: only ``id`` is needed here, and loading the
        # full entity would eagerly decrypt credential_ciphertext for
        # no reason.
        account_id = (
            session.query(EmailAccount.id)
            .filter(
                EmailAccount.user_id == user_id,
                EmailAccount.deleted == False,
            )
            .scalar()
        )
        if account_id is None:
            return {
                "active": False, "current": 0, "total": 0, "progress": 0,
                "label": "", "unit": "messages",
                "success": None, "message": "",
            }

    return email_sync_progress_read(account_id)


def _do_disconnect(user_id: int) -> dict:
    """Cascade-delete all email data for one user's linked accounts.

    Cancels any in-flight sync first (best-effort — the thread only
    notices between chunks, not mid-chunk).
    """
    from .sync_cancellation import cancel_sync

    with session_scope() as session:
        # Column-only: only ``id`` is needed to cancel/cascade-delete
        # and mark deleted — loading full entities would eagerly
        # decrypt credential_ciphertext for rows we're only deleting.
        account_ids = [
            row[0] for row in (
                session.query(EmailAccount.id)
                .filter(
                    EmailAccount.user_id == user_id,
                    EmailAccount.deleted == False,
                )
                .all()
            )
        ]

        for acct_id in account_ids:
            cancel_sync(acct_id)
            cascade_delete_email_data(session, acct_id, user_id)

        if account_ids:
            session.query(EmailAccount).filter(
                EmailAccount.id.in_(account_ids),
            ).update(
                {"deleted": True},
                synchronize_session=False,
            )
        session.commit()
    return {"success": True}


# ---- HTTP Routes ---------------------------------------------------------


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/connect/{user_id}")
async def email_connect(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """Link a Fastmail account. Body: {token, email_address}."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if EMAIL_CONNECT_DISABLED:
        raise HTTPException(
            status_code=503, detail=EMAIL_CONNECT_DISABLED_MESSAGE,
        )

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400, detail="Invalid JSON body",
        ) from None

    token = (body.get("token") or "").strip()
    email_address = (body.get("email_address") or "").strip()
    if not token or not email_address:
        raise HTTPException(
            status_code=400,
            detail="token and email_address are required",
        )

    validated = await validate_fastmail_token(token)
    if validated is None:
        raise HTTPException(
            status_code=401, detail="Invalid Fastmail API token",
        )

    _, result = await asyncio.to_thread(
        _do_connect, user_id, token, validated,
    )
    return result


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/status/{user_id}")
async def email_status(request: Request, user_id: int) -> dict[str, Any]:
    """Return email connection status for the authenticated user."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return await asyncio.to_thread(_do_status, user_id)


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/disconnect/{user_id}")
async def email_disconnect(request: Request, user_id: int) -> dict[str, Any]:
    """Disconnect email and cascade-delete all derived data."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return await asyncio.to_thread(_do_disconnect, user_id)


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/sync-progress/{user_id}")
async def email_sync_progress(
    request: Request, user_id: int,
) -> dict[str, Any]:
    """Return live email-sync progress for the authenticated user."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return await asyncio.to_thread(_do_sync_progress, user_id)
