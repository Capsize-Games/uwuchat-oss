"""Auth extension — admin (superuser-only) routes.

Endpoints:
  GET  /api/v1/auth/admin/accounts        — list accounts
  GET  /api/v1/auth/admin/accounts/{id}   — get one account
  PATCH /api/v1/auth/admin/accounts/{id}  — update account flags
  POST /api/v1/auth/admin/accounts/{id}/disable
  POST /api/v1/auth/admin/accounts/{id}/enable
  POST /api/v1/auth/admin/accounts/create
  POST /api/v1/auth/admin/accounts/{id}/suspend
  POST /api/v1/auth/admin/accounts/{id}/reactivate
  DELETE /api/v1/auth/admin/accounts/{id}
  POST /api/v1/auth/admin/accounts/{id}/reset-usage
  POST /api/v1/auth/admin/accounts/{id}/set-usage
  GET  /api/v1/auth/admin/accounts/{id}/usage-count
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func

from airunner_services.database.session import public_session_scope
from airunner_services.data.tenant import tenant_schema_for_key
from extensions.auth.server.dependencies import require_auth, require_superuser
from extensions.auth.server.limiter import limiter
from extensions.auth.server.models import Account

router = APIRouter()

# ── Admin (superuser-only) ──────────────────────────────────────────
#
# Every route below is gated by ``Depends(require_superuser)`` (401 when
# unauthenticated, 403 when not a superuser). The frontend ``/admin`` gate
# is UX only — this dependency is the real security boundary. Promote an
# account with::
#
#     ./scripts/docker.sh auth promote --email you@example.com


class AdminAccountResponse(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool
    is_verified: bool
    is_superuser: bool
    is_suspended: bool
    auth_provider: str


class AdminAccountDetailResponse(AdminAccountResponse):
    tenant_schema: str
    created_at: str | None = None
    last_login: str | None = None


class AdminAccountListResponse(BaseModel):
    accounts: list[AdminAccountResponse]
    total: int
    limit: int
    offset: int


class AdminUpdateAccountRequest(BaseModel):
    """Patch body for editable account flags.

    Only the three boolean flags below may be edited here — ``email`` and
    ``password_hash`` are intentionally not editable through this route.
    All fields are optional; omitted fields are left unchanged.
    """

    is_active: bool | None = None
    is_verified: bool | None = None
    is_superuser: bool | None = None
    is_suspended: bool | None = None


class AdminCreateAccountRequest(BaseModel):
    email: str
    username: str = ""  # Optional — auto-generated if empty
    password: str
    is_superuser: bool = False
    is_verified: bool = True


class AdminCreateAccountResponse(AdminAccountResponse):
    tenant_schema: str


class AdminDeleteResponse(BaseModel):
    id: int
    message: str
    tenant_schema: str


def _account_response(account: Account) -> AdminAccountResponse:
    return AdminAccountResponse(
        id=account.id,
        email=account.email,
        username=account.username,
        is_active=bool(account.is_active),
        is_verified=bool(account.is_verified),
        is_superuser=bool(account.is_superuser),
        is_suspended=bool(account.is_suspended),
        auth_provider=account.auth_provider,
    )


def _account_detail(account: Account) -> AdminAccountDetailResponse:
    return AdminAccountDetailResponse(
        id=account.id,
        email=account.email,
        username=account.username,
        is_active=bool(account.is_active),
        is_verified=bool(account.is_verified),
        is_superuser=bool(account.is_superuser),
        is_suspended=bool(account.is_suspended),
        auth_provider=account.auth_provider,
        tenant_schema=account.tenant_schema,
        created_at=(
            account.created_at.isoformat() if account.created_at else None
        ),
        last_login=(
            account.last_login.isoformat() if account.last_login else None
        ),
    )


@router.get(
    "/admin/accounts",
    summary="List accounts with pagination/search (superuser only)",
    response_model=AdminAccountListResponse,
)
@limiter.limit("60/minute")
async def admin_list_accounts(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    _admin_id: int = Depends(require_superuser),
) -> AdminAccountListResponse:
    """Return accounts, optionally filtered by an email/username substring.

    Supports ``?limit=&offset=`` pagination (limit clamped to 1–200) and an
    optional ``?q=`` case-insensitive match on email or username.
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    with public_session_scope() as session:
        query = session.query(Account)
        if q:
            needle = f"%{q.strip().lower()}%"
            query = query.filter(
                func.lower(Account.email).like(needle)
                | func.lower(Account.username).like(needle)
            )
        total = query.count()
        accounts = (
            query.order_by(Account.id).offset(offset).limit(limit).all()
        )
        return AdminAccountListResponse(
            accounts=[_account_response(a) for a in accounts],
            total=total,
            limit=limit,
            offset=offset,
        )


@router.get(
    "/admin/accounts/{account_id}",
    summary="Get a single account's detail (superuser only)",
    response_model=AdminAccountDetailResponse,
)
@limiter.limit("60/minute")
async def admin_get_account(
    request: Request,
    account_id: int,
    _admin_id: int = Depends(require_superuser),
) -> AdminAccountDetailResponse:
    """Return full detail for one account."""
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.id == account_id)
            .first()
        )
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        return _account_detail(account)


@router.patch(
    "/admin/accounts/{account_id}",
    summary="Toggle is_active/is_verified/is_superuser (superuser only)",
    response_model=AdminAccountDetailResponse,
)
@limiter.limit("30/minute")
async def admin_update_account(
    request: Request,
    account_id: int,
    body: AdminUpdateAccountRequest,
    admin_id: int = Depends(require_superuser),
) -> AdminAccountDetailResponse:
    """Edit an account's boolean flags.

    Admins cannot demote (remove superuser), disable, or suspend their
    **own** account here — that guards against locking the last admin out.
    """
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.id == account_id)
            .first()
        )
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")

        if account.id == admin_id:
            if body.is_superuser is False:
                raise HTTPException(
                    status_code=400,
                    detail="You cannot remove your own superuser status",
                )
            if body.is_active is False:
                raise HTTPException(
                    status_code=400,
                    detail="You cannot disable your own account",
                )
            if body.is_suspended is True:
                raise HTTPException(
                    status_code=400,
                    detail="You cannot suspend your own account",
                )

        if body.is_active is not None:
            account.is_active = body.is_active
        if body.is_verified is not None:
            account.is_verified = body.is_verified
        if body.is_superuser is not None:
            account.is_superuser = body.is_superuser
        if body.is_suspended is not None:
            account.is_suspended = body.is_suspended
        session.add(account)
        session.flush()
        return _account_detail(account)


def _set_active(account_id: int, admin_id: int, active: bool) -> AdminAccountDetailResponse:
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.id == account_id)
            .first()
        )
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        if not active and account.id == admin_id:
            raise HTTPException(
                status_code=400,
                detail="You cannot disable your own account",
            )
        account.is_active = active
        session.add(account)
        session.flush()
        return _account_detail(account)


@router.post(
    "/admin/accounts/{account_id}/disable",
    summary="Disable an account (superuser only)",
    response_model=AdminAccountDetailResponse,
)
@limiter.limit("30/minute")
async def admin_disable_account(
    request: Request,
    account_id: int,
    admin_id: int = Depends(require_superuser),
) -> AdminAccountDetailResponse:
    """Set ``is_active = False`` for the account."""
    return _set_active(account_id, admin_id, False)


@router.post(
    "/admin/accounts/{account_id}/enable",
    summary="Enable an account (superuser only)",
    response_model=AdminAccountDetailResponse,
)
@limiter.limit("30/minute")
async def admin_enable_account(
    request: Request,
    account_id: int,
    admin_id: int = Depends(require_superuser),
) -> AdminAccountDetailResponse:
    """Set ``is_active = True`` for the account."""
    return _set_active(account_id, admin_id, True)


@router.post(
    "/admin/accounts",
    status_code=status.HTTP_201_CREATED,
    summary="Create an account server-side (superuser only)",
    response_model=AdminCreateAccountResponse,
)
@limiter.limit("10/minute")
async def admin_create_account(
    request: Request,
    body: AdminCreateAccountRequest,
    _admin_id: int = Depends(require_superuser),
) -> AdminCreateAccountResponse:
    """Create a new local account and provision its tenant schema.

    Reuses :func:`create_account` — the exact path the management CLI
    takes — so the two can't drift.
    """
    try:
        account_id, tenant_schema = create_account(
            body.email,
            body.password,
            body.username if body.username.strip() else None,
            is_superuser=body.is_superuser,
            is_verified=body.is_verified,
        )
    except AccountConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except AccountValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.id == account_id)
            .first()
        )
        return AdminCreateAccountResponse(
            **_account_response(account).model_dump(),
            tenant_schema=tenant_schema,
        )


def _set_suspended(
    account_id: int, admin_id: int, suspended: bool
) -> AdminAccountDetailResponse:
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.id == account_id)
            .first()
        )
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        if suspended and account.id == admin_id:
            raise HTTPException(
                status_code=400,
                detail="You cannot suspend your own account",
            )
        account.is_suspended = suspended
        session.add(account)
        session.flush()
        return _account_detail(account)


@router.post(
    "/admin/accounts/{account_id}/suspend",
    summary="Suspend an account (superuser only)",
    response_model=AdminAccountDetailResponse,
)
@limiter.limit("30/minute")
async def admin_suspend_account(
    request: Request,
    account_id: int,
    admin_id: int = Depends(require_superuser),
) -> AdminAccountDetailResponse:
    """Set ``is_suspended = True`` for the account."""
    return _set_suspended(account_id, admin_id, True)


@router.post(
    "/admin/accounts/{account_id}/reactivate",
    summary="Reactivate a suspended account (superuser only)",
    response_model=AdminAccountDetailResponse,
)
@limiter.limit("30/minute")
async def admin_reactivate_account(
    request: Request,
    account_id: int,
    admin_id: int = Depends(require_superuser),
) -> AdminAccountDetailResponse:
    """Set ``is_suspended = False`` for the account."""
    return _set_suspended(account_id, admin_id, False)


def _drop_tenant_schema(schema_name: str) -> None:
    """Drop a PostgreSQL tenant schema and all its contents.

    Uses a one-shot engine (NullPool) so no connection leaks into the
    application pool.  Errors are logged but not raised — the account
    row has already been deleted and a leftover schema is a minor leak.
    """
    import logging

    from sqlalchemy import pool, text

    from airunner_services.conf import settings
    from airunner_services.database.db.engine import (
        create_configured_engine,
    )

    logger = logging.getLogger(__name__)
    db_url = str(settings.DATABASE_URL) if settings.DATABASE_URL else ""
    if not db_url:
        logger.error("Cannot drop schema '%s': no DATABASE_URL configured", schema_name)
        return
    # Never touch the public schema.
    if schema_name in ("public", ""):
        return
    engine = None
    try:
        engine = create_configured_engine(db_url, poolclass=pool.NullPool)
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
    except Exception:
        logger.exception("Failed to drop tenant schema '%s'", schema_name)
    finally:
        if engine is not None:
            engine.dispose()


@router.delete(
    "/admin/accounts/{account_id}",
    summary="Delete an account and its tenant schema (superuser only)",
    response_model=AdminDeleteResponse,
)
@limiter.limit("30/minute")
async def admin_delete_account(
    request: Request,
    account_id: int,
    admin_id: int = Depends(require_superuser),
) -> AdminDeleteResponse:
    """Hard-delete the account row and drop its tenant schema.

    This is a permanent, irreversible operation.  All user data in the
    tenant schema is destroyed.  Admins cannot delete their own account.
    """
    if account_id == admin_id:
        raise HTTPException(
            status_code=400,
            detail="You cannot delete your own account",
        )
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.id == account_id)
            .first()
        )
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        tenant_schema = account.tenant_schema

        # Clean up related rows in public-schema tables that hold
        # foreign keys referencing accounts.id, otherwise the
        # account delete fails with an integrity error.
        from airunner_services.database.models.pipeline_token_usage import (
            PipelineTokenUsage,
        )
        from extensions.auth.server.waitlist_entry import (
            WaitlistEntry,
        )
        from extensions.auth.server.password_reset_token import (
            PasswordResetToken,
        )

        # Delete PipelineTokenUsage (pure usage tracking, no retention value)
        session.query(PipelineTokenUsage).filter(
            PipelineTokenUsage.account_id == account_id,
        ).delete(synchronize_session=False)

        # Anonymise WaitlistEntry (keep row, drop account linkage)
        session.query(WaitlistEntry).filter(
            WaitlistEntry.converted_account_id == account_id,
        ).update(
            {"converted_account_id": None},
            synchronize_session=False,
        )

        session.query(PasswordResetToken).filter(
            PasswordResetToken.account_id == account_id,
        ).delete()

        session.delete(account)

    # Drop the tenant schema so a re-registration with the same OAuth
    # provider cannot land on the old schema and resurrect stale data.
    _drop_tenant_schema(tenant_schema)

    return AdminDeleteResponse(
        id=account_id,
        message=(
            f"Account deleted and tenant schema "
            f"'{tenant_schema}' dropped."
        ),
        tenant_schema=tenant_schema,
    )


class AdminResetUsageResponse(BaseModel):
    message: str
    deleted_count: int


@router.post(
    "/admin/accounts/{account_id}/reset-usage",
    summary="Reset message usage for one account (superuser only)",
    response_model=AdminResetUsageResponse,
)
@limiter.limit("10/minute")
async def admin_reset_usage(
    request: Request,
    account_id: int,
    _admin_id: int = Depends(require_superuser),
) -> AdminResetUsageResponse:
    """Mark all PipelineTokenUsage rows for the account as skipped
    so the user's quota resets to zero."""
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.id == account_id)
            .first()
        )
        if account is None:
            raise HTTPException(
                status_code=404, detail="Account not found",
            )
        tenant_key = account.tenant_schema

    from airunner_services.database.models.pipeline_token_usage import (
        PipelineTokenUsage,
    )
    from airunner_services.database.session import (
        session_scope as tenant_session,
    )

    deleted = 0
    with tenant_session() as ts:
        deleted = (
            ts.query(PipelineTokenUsage)
            .filter(
                PipelineTokenUsage.tenant_key == tenant_key,
                PipelineTokenUsage.skipped.is_(False),
            )
            .update({"skipped": True}, synchronize_session=False)
        )
        ts.commit()

    return AdminResetUsageResponse(
        message=f"Reset {deleted} usage records",
        deleted_count=deleted,
    )


class AdminSetUsageRequest(BaseModel):
    target_count: int


@router.post(
    "/admin/accounts/{account_id}/set-usage",
    summary="Set message usage count for one account (superuser only)",
    response_model=AdminResetUsageResponse,
)
@limiter.limit("10/minute")
async def admin_set_usage(
    request: Request,
    account_id: int,
    body: AdminSetUsageRequest,
    _admin_id: int = Depends(require_superuser),
) -> AdminResetUsageResponse:
    """Adjust ``PipelineTokenUsage`` skipped flags so the account's
    active message count equals ``target_count``."""
    target = max(0, body.target_count)

    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.id == account_id)
            .first()
        )
        if account is None:
            raise HTTPException(
                status_code=404, detail="Account not found",
            )
        tenant_key = account.tenant_schema

    from airunner_services.database.models.pipeline_token_usage import (
        PipelineTokenUsage,
    )
    from airunner_services.database.session import (
        session_scope as tenant_session,
    )

    with tenant_session() as ts:
        records = (
            ts.query(PipelineTokenUsage)
            .filter(
                PipelineTokenUsage.tenant_key == tenant_key,
                PipelineTokenUsage.call_chain_id.isnot(None),
            )
            .order_by(PipelineTokenUsage.recorded_at.desc())
            .all()
        )

        current_active = sum(
            1 for r in records if not r.skipped
        )

        if target < current_active:
            # Un-skip enough records to reach target
            to_skip = current_active - target
            skipped = 0
            for r in records:
                if skipped >= to_skip:
                    break
                if not r.skipped:
                    r.skipped = True
                    skipped += 1
        else:
            # Increase count: first unskip existing records, then
            # create synthetic ones if needed.
            to_unskip = target - current_active
            unskipped = 0
            for r in records:
                if unskipped >= to_unskip:
                    break
                if r.skipped:
                    r.skipped = False
                    unskipped += 1

            # If we still need more, insert synthetic records.
            still_needed = to_unskip - unskipped
            if still_needed > 0:
                from datetime import datetime as _dt
                from uuid import uuid4
                now = _dt.utcnow()
                for _ in range(still_needed):
                    ts.add(PipelineTokenUsage(
                        pipeline_key="admin_set_usage",
                        model_id="admin",
                        tenant_key=tenant_key,
                        call_chain_id=str(uuid4()),
                        input_tokens=0,
                        output_tokens=0,
                        skipped=False,
                        recorded_at=now,
                    ))

        ts.commit()
        changed = abs(target - current_active)

    return AdminResetUsageResponse(
        message=(
            f"Set usage to {target} (was {current_active},"
            f" changed {changed} records)"
        ),
        deleted_count=changed,
    )


@router.get(
    "/admin/accounts/{account_id}/usage-count",
    summary="Get message count for one account (superuser only)",
)
@limiter.limit("60/minute")
async def admin_get_usage_count(
    request: Request,
    account_id: int,
    _admin_id: int = Depends(require_superuser),
) -> dict:
    """Return the current active message count for one account."""
    import importlib
    import os

    project = os.environ.get("AIRUNNER_PROJECT", "")
    if not project:
        from airunner_services.conf import settings

        project = getattr(settings, "AIRUNNER_PROJECT", "") or ""
    if not project:
        return {"turns_used": 0}
    try:
        mod = importlib.import_module(
            f"projects.{project}.server.quota_service"
        )
        q = mod.get_quota(account_id)
    except ImportError:
        return {"turns_used": 0}
    return {"turns_used": q["turns_used"]}
