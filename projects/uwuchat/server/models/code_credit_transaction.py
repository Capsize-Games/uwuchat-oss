"""UwUChat code-credits debit ledger.

Lives in the **public** schema (like ``accounts``) so the balance and
audit trail are shared across all tenants and readable before tenant
context is established.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.sql import func

from airunner_services.database.base import Base


class CodeCreditTransaction(Base):
    """One ledger row: a top-up or a headlesscode session debit.

    ``amount_usd`` is negative for debits and positive for top-ups.
    ``session_id`` is set for ``"session_debit"`` rows and is the
    idempotency key for :func:`debit_session_usage` (a crashed/retried
    poller must not double-debit one session).
    """

    __tablename__ = "code_credit_transactions"
    __public_schema__ = True
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(
        Integer, ForeignKey("accounts.id"), nullable=False, index=True
    )
    amount_usd = Column(Numeric(10, 4), nullable=False)
    kind = Column(String(16), nullable=False)
    session_id = Column(String(64), nullable=True, index=True)
    note = Column(String(255), nullable=True)
    created_at = Column(
        DateTime, nullable=False, server_default=func.now()
    )


__all__ = ["CodeCreditTransaction"]
