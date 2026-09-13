"""WebSocket RPC handlers for the admin code-credits endpoints.

The client's ``request()`` helper (``api/client-base.ts``) sends every
call over the shared RPC-over-WebSocket channel — ``code_credits_
routes.py``'s FastAPI HTTP router is unreachable from the real client
(see wiki/WebSocket-RPC.md gotcha #4). These handlers are the actual
ones the admin credits UI would need to talk to; mirrors
``headlesscode_rpc.py``'s pattern (thin wrappers over the same
service module the HTTP routes use, service-level errors mapped onto
RPC status codes).

Superuser-gated, matching the HTTP routes' ``require_superuser``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from airunner_services.api.routes.events import _rpc_register
from airunner_services.database.session import public_session_scope
from projects.uwuchat.server.code_credits_service import (
    add_credits,
    remaining_budget_usd,
)
from projects.uwuchat.server.models.code_credit_transaction import (
    CodeCreditTransaction,
)

_UNAUTHORIZED = {"status": 403, "body": {"error": "Admin access required"}}


def _transaction_to_dict(tx: CodeCreditTransaction) -> dict:
    """Serialize one ledger row for the admin display.

    Duplicated from code_credits_routes.py (that module's HTTP router
    is dead code from the client's perspective — see this module's
    docstring) rather than imported, matching this codebase's existing
    convention of duplicating small private per-module helpers (e.g.
    ``_require_superuser`` across the other rpc_*.py modules).
    """
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


def _require_superuser(ws: Any) -> int | None:
    """Return the authenticated account_id if superuser, or None."""
    try:
        from airunner_services.api.ws_tenant import resolve_ws_tenant

        _tenant, account_id = resolve_ws_tenant(ws)
        if account_id is None:
            return None
        from extensions.auth.server.models import Account

        acct = Account.objects.get(account_id)
        if acct is None or not getattr(acct, "is_superuser", False):
            return None
        return account_id
    except Exception:
        return None


@_rpc_register("GET", "/api/v1/uwuchat/code-credits/{account_id}")
async def _rpc_get_code_credits(body: dict, **kw: Any) -> dict[str, Any]:
    """Return the spendable balance and recent transactions."""
    if _require_superuser(kw.get("ws")) is None:
        return _UNAUTHORIZED
    pp: dict = kw.get("path_params", {})
    raw_id = pp.get("account_id", "")
    if not raw_id.isdigit():
        return {"status": 400, "body": {"error": "Invalid account_id"}}
    account_id = int(raw_id)
    try:
        balance = remaining_budget_usd(account_id)
    except ValueError as exc:
        return {"status": 404, "body": {"error": str(exc)}}
    with public_session_scope() as session:
        transactions = (
            session.query(CodeCreditTransaction)
            .filter(CodeCreditTransaction.account_id == account_id)
            .order_by(CodeCreditTransaction.id.desc())
            .limit(20)
            .all()
        )
        recent = [_transaction_to_dict(tx) for tx in transactions]
    return {
        "status": 200,
        "body": {
            "balance_usd": str(balance),
            "recent_transactions": recent,
        },
    }


@_rpc_register("POST", "/api/v1/uwuchat/code-credits/{account_id}/topup")
async def _rpc_top_up_code_credits(body: dict, **kw: Any) -> dict[str, Any]:
    """Manually top up an account's code-credits balance."""
    if _require_superuser(kw.get("ws")) is None:
        return _UNAUTHORIZED
    pp: dict = kw.get("path_params", {})
    raw_id = pp.get("account_id", "")
    if not raw_id.isdigit():
        return {"status": 400, "body": {"error": "Invalid account_id"}}
    try:
        amount = Decimal(str(body.get("amount_usd", "")))
    except Exception:
        return {
            "status": 400,
            "body": {"error": "amount_usd must be a decimal string"},
        }
    if amount <= 0:
        return {
            "status": 400,
            "body": {"error": "amount_usd must be positive"},
        }
    try:
        new_balance = add_credits(
            int(raw_id), amount, note=str(body.get("note", "")),
        )
    except ValueError as exc:
        return {"status": 404, "body": {"error": str(exc)}}
    return {"status": 200, "body": {"balance_usd": str(new_balance)}}
