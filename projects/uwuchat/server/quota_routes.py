"""Quota API routes — mounted at /api/v1/usage."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from airunner_services.database.session import public_session_scope
from extensions.auth.server.dependencies import require_auth
from extensions.auth.server.models import Account
from projects.uwuchat.server.quota_service import QuotaResult, get_quota

router = APIRouter()


@router.get("/quota", response_model=QuotaResult)
async def get_usage_quota(
    preview_tier: str | None = Query(None),
    account_id: int = Depends(require_auth),
) -> QuotaResult:
    """Return current turn quota for the authenticated user.

    Superusers may pass ?preview_tier=<slug> to simulate a tier.
    Non-superusers get 403 if preview_tier is supplied.
    """
    if preview_tier is not None:
        with public_session_scope() as session:
            acct = session.get(Account, account_id)
            if acct is None or not acct.is_superuser:
                raise HTTPException(
                    403, "preview_tier requires superuser"
                )
    try:
        return get_quota(account_id, preview_tier=preview_tier)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
