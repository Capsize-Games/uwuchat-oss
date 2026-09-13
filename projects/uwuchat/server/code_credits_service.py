"""Real-dollar prepaid balance for admin headlesscode sessions.

The balance is **denormalized** on ``Account.code_credits_usd``
(public schema) and kept in sync with the ``code_credit_transactions``
ledger inside the same DB transaction, so the two can never drift.
``get_balance`` reads the column (fast); the ledger is the audit trail
and the idempotency source for session debits.

All money values are ``Decimal``/``Numeric`` — never ``float`` — to
avoid drift across many small sub-cent debits.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select, update

from airunner_services.database.session import public_session_scope
from extensions.auth.server.models import Account
from projects.uwuchat.server.models.code_credit_transaction import (
    CodeCreditTransaction,
)

_ZERO = Decimal("0")


def _to_decimal(value: Decimal | str | float) -> Decimal:
    """Coerce a money value to Decimal without binary-float drift."""
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


def get_balance(account_id: int) -> Decimal:
    """Return the account's current raw balance.

    May be slightly negative after a final session debit overshoots
    the remaining balance — see :func:`remaining_budget_usd`.
    """
    with public_session_scope() as session:
        balance = session.execute(
            select(Account.code_credits_usd).where(
                Account.id == account_id
            )
        ).scalar_one_or_none()
    if balance is None:
        raise ValueError(f"Account {account_id} not found")
    return _to_decimal(balance)


def _apply(
    account_id: int,
    delta_usd: Decimal,
    *,
    kind: str,
    session_id: str | None = None,
    note: str | None = None,
) -> Decimal:
    """Insert one ledger row and update the running total atomically."""
    with public_session_scope() as session:
        existing = session.get(Account, account_id)
        if existing is None:
            raise ValueError(f"Account {account_id} not found")
        session.add(
            CodeCreditTransaction(
                account_id=account_id,
                amount_usd=delta_usd,
                kind=kind,
                session_id=session_id,
                note=note,
            )
        )
        new_balance = session.execute(
            update(Account)
            .where(Account.id == account_id)
            .values(
                code_credits_usd=(
                    Account.code_credits_usd + delta_usd
                )
            )
            .returning(Account.code_credits_usd)
        ).scalar_one()
    return _to_decimal(new_balance)


def session_debits_total(account_id: int, session_id: str) -> Decimal:
    """Return the total already-debited cost for one session.

    The sum of prior ``session_debit`` ledger rows — the delta baseline
    :func:`reconcile_session_usage` needs so repeated polls never debit
    the same spend twice.
    """
    with public_session_scope() as session:
        total = session.execute(
            select(
                func.coalesce(
                    func.sum(CodeCreditTransaction.amount_usd), 0
                )
            ).where(
                CodeCreditTransaction.account_id == account_id,
                CodeCreditTransaction.kind == "session_debit",
                CodeCreditTransaction.session_id == session_id,
            )
        ).scalar_one()
    return _to_decimal(total) * -1


def add_credits(
    account_id: int, amount_usd: Decimal, *, note: str
) -> Decimal:
    """Admin-only manual top-up. Rejects amount_usd <= 0."""
    amount = _to_decimal(amount_usd)
    if amount <= 0:
        raise ValueError("amount_usd must be positive")
    return _apply(
        account_id, amount, kind="topup", note=note
    )


def debit_session_usage(
    account_id: int, session_id: str, cost_usd: Decimal
) -> Decimal:
    """Idempotent debit of one headlesscode session's real cost.

    Safe to call more than once for the same ``session_id`` — the
    ledger's ``session_debit`` rows are the idempotency key, so a
    repeat call no-ops instead of double-debiting.
    """
    cost = _to_decimal(cost_usd)
    if cost < 0:
        raise ValueError("cost_usd must not be negative")
    if cost == 0:
        return get_balance(account_id)
    if session_debits_total(account_id, session_id) > 0:
        return get_balance(account_id)
    return _apply(
        account_id,
        -cost,
        kind="session_debit",
        session_id=session_id,
    )


def debit_session_delta(
    account_id: int,
    session_id: str,
    delta_usd: Decimal,
    *,
    note: str | None = None,
) -> Decimal:
    """Record one delta debit for an in-flight session.

    Used by the reconciler, which already computed ``delta_usd`` as the
    gap between the current usage-file cost and the sum of prior
    ``session_debit`` rows. Non-positive deltas are no-ops.
    """
    delta = _to_decimal(delta_usd)
    if delta <= 0:
        return get_balance(account_id)
    return _apply(
        account_id,
        -delta,
        kind="session_debit",
        session_id=session_id,
        note=note,
    )


def remaining_budget_usd(account_id: int) -> Decimal:
    """Current balance, clamped to >= 0.

    This is the value to pass as ``HEADLESSCODE_MAX_COST_USD`` when
    launching a session for this account.
    """
    return max(get_balance(account_id), _ZERO)


def has_credits(account_id: int) -> bool:
    """False when remaining_budget_usd() <= 0.

    The gate a future session launcher must check before starting a
    new headlesscode session.
    """
    return remaining_budget_usd(account_id) > 0
