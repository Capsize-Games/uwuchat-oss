"""Email stats endpoint — post-sync aggregate rollups for the profile
panel. Split out of routes.py to stay under the project's line limit.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from airunner_services.api.routes.events import _rpc_register
from airunner_services.database.models.email_account import EmailAccount
from airunner_services.database.models.email_stats import EmailStats
from airunner_services.database.session import session_scope
from extensions.auth.server.dependencies import require_auth

router = APIRouter()

_EMPTY_STATS = {
    "available": False,
    "total_messages": 0,
    "sent_count": 0,
    "received_count": 0,
    "top_contacts": [],
    "computed_at": None,
}


def _do_email_stats(user_id: int) -> dict[str, Any]:
    """Return the ``all_time`` EmailStats row for one user's account.

    Column-only query: only ``id`` is needed here, and loading the
    full entity would eagerly decrypt credential_ciphertext for no
    reason (requiring an active DEK this read-only stats panel has
    no reason to depend on).
    """
    with session_scope() as session:
        account_id = (
            session.query(EmailAccount.id)
            .filter(
                EmailAccount.user_id == user_id,
                EmailAccount.deleted == False,
            )
            .scalar()
        )
        if account_id is None:
            return dict(_EMPTY_STATS)

        row = (
            session.query(EmailStats)
            .filter(
                EmailStats.email_account_id == account_id,
                EmailStats.period == "all_time",
            )
            .first()
        )
        if row is None:
            return dict(_EMPTY_STATS)

        return {
            "available": True,
            "total_messages": row.total_messages,
            "sent_count": row.sent_count,
            "received_count": row.received_count,
            "top_contacts": row.top_contacts or [],
            "computed_at": (
                row.computed_at.isoformat() if row.computed_at else None
            ),
        }


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/stats/{user_id}")
async def email_stats(
    request: Request, user_id: int,
) -> dict[str, Any]:
    """Return aggregate email stats for the authenticated user."""
    from fastapi import HTTPException

    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    import asyncio

    return await asyncio.to_thread(_do_email_stats, user_id)


@_rpc_register("GET", "/api/v1/email/stats/{user_id}")
async def _rpc_email_stats(body: dict, **kw: Any) -> dict[str, Any]:
    """RPC handler for email stats — the frontend's actual transport."""
    import asyncio

    from airunner_services.api.ws_tenant import resolve_ws_tenant

    ws = kw.get("ws")
    path_params = kw.get("path_params", {})
    user_id = int(path_params.get("user_id", 0))

    account_id = None
    if ws is not None:
        _tenant, account_id = resolve_ws_tenant(ws)
    if account_id is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}
    if account_id != user_id:
        return {"status": 403, "body": {"error": "Forbidden"}}

    result = await asyncio.to_thread(_do_email_stats, user_id)
    return {"status": 200, "body": result}
