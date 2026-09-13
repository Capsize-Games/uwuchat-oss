"""Admin-only UwUChat code-credits API routes.

Mounted at ``/api/v1/uwuchat/code-credits``. Every endpoint is gated
by :func:`require_superuser`. There is no purchase/Stripe flow in this
phase — manual admin top-up is the whole top-up mechanism.

All money values are returned as strings (never floats) so JSON
serialization cannot surprise on decimal precision.
"""

from __future__ import annotations

import importlib
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from airunner_services.database.session import public_session_scope
from extensions.auth.server.dependencies import require_superuser
from projects.uwuchat.server.code_credits_service import (
    add_credits,
    remaining_budget_usd,
)
from projects.uwuchat.server.models.code_credit_transaction import (
    CodeCreditTransaction,
)

router = APIRouter()


class TopUpRequest(BaseModel):
    """Body for the admin top-up endpoint."""

    amount_usd: str
    note: str = ""


def _transaction_to_dict(tx: CodeCreditTransaction) -> dict:
    """Serialize one ledger row for the admin display."""
    return {
        "id": tx.id,
        "amount_usd": str(tx.amount_usd),
        "kind": tx.kind,
        "session_id": tx.session_id,
        "note": tx.note,
        "created_at": (
            tx.created_at.isoformat() if tx.created_at else None
        ),
    }


@router.get("/{account_id}")
async def get_code_credits(
    account_id: int,
    _admin_id: int = Depends(require_superuser),
) -> dict:
    """Return the spendable balance and recent transactions."""
    try:
        balance = remaining_budget_usd(account_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    with public_session_scope() as session:
        transactions = (
            session.query(CodeCreditTransaction)
            .filter(
                CodeCreditTransaction.account_id == account_id
            )
            .order_by(CodeCreditTransaction.id.desc())
            .limit(20)
            .all()
        )
        # Serialize inside the session scope — the instances are
        # detached once the scope closes.
        recent = [_transaction_to_dict(tx) for tx in transactions]
    return {
        "balance_usd": str(balance),
        "recent_transactions": recent,
    }


@router.post("/{account_id}/topup")
async def top_up_code_credits(
    account_id: int,
    payload: TopUpRequest,
    _admin_id: int = Depends(require_superuser),
) -> dict:
    """Manually top up an account's code-credits balance."""
    try:
        amount = Decimal(payload.amount_usd)
    except Exception:
        raise HTTPException(400, "amount_usd must be a decimal string")
    if amount <= 0:
        raise HTTPException(400, "amount_usd must be positive")
    try:
        new_balance = add_credits(
            account_id, amount, note=payload.note
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"balance_usd": str(new_balance)}


# Importing by name (not binding it) runs the @_rpc_register decorators
# in code_credits_rpc.py — same convention as headlesscode_routes.py.
# This HTTP router is unreachable from the real client (WS-RPC-only
# architecture, see wiki/WebSocket-RPC.md gotcha #4); code_credits_rpc
# is what the admin credits UI actually needs.
importlib.import_module(
    "projects.uwuchat.server.routes.code_credits_rpc"
)
