"""Integration tests for the UwUchat code-credits service.

These hit the real public schema (the dev database), mirroring the
auth route tests — the balance/ledger sync under test only means
something against real tables.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from airunner_services.contract_enums import ModelService
from airunner_services.database.session import public_session_scope
from extensions.auth.server.models import Account
from projects.uwuchat.server.code_credits_service import (
    add_credits,
    debit_session_usage,
    get_balance,
    has_credits,
    remaining_budget_usd,
)
from projects.uwuchat.server.models.code_credit_transaction import (
    CodeCreditTransaction,
)


@pytest.fixture()
def account_id() -> int:
    """Scratch public-schema account, removed after the test."""
    with public_session_scope() as session:
        acct = Account(
            email=f"cc-{uuid.uuid4().hex[:8]}@example.com",
            username=f"cc_{uuid.uuid4().hex[:8]}",
            password_hash="unused",
            tenant_schema=f"tenant_{uuid.uuid4().hex}",
            auth_provider=ModelService.LOCAL.value,
        )
        session.add(acct)
        session.flush()
        acct_id = int(acct.id)
    yield acct_id
    with public_session_scope() as session:
        existing = session.get(Account, acct_id)
        if existing is not None:
            session.delete(existing)


def _tx_count(
    session, account_id: int, kind: str, session_id: str | None = None
) -> int:
    """Count ledger rows for one account/kind, optionally per session."""
    query = session.query(CodeCreditTransaction).filter(
        CodeCreditTransaction.account_id == account_id,
        CodeCreditTransaction.kind == kind,
    )
    if session_id is not None:
        query = query.filter(
            CodeCreditTransaction.session_id == session_id
        )
    return query.count()


def test_balance_starts_at_zero(_db: str, account_id: int) -> None:
    """A fresh account has a zero balance."""
    assert get_balance(account_id) == Decimal("0")


def test_add_credits_increases_balance_and_ledger(
    _db: str, account_id: int,
) -> None:
    """Top-up updates both the balance and the audit ledger."""
    new_balance = add_credits(
        account_id, Decimal("25.50"), note="test top-up"
    )
    assert new_balance == Decimal("25.5000")
    assert get_balance(account_id) == Decimal("25.5000")
    with public_session_scope() as session:
        assert _tx_count(session, account_id, "topup") == 1
        tx = (
            session.query(CodeCreditTransaction)
            .filter(
                CodeCreditTransaction.kind == "topup",
                CodeCreditTransaction.account_id == account_id,
            )
            .one()
        )
        assert tx.amount_usd == Decimal("25.5000")
        assert tx.note == "test top-up"
        assert tx.session_id is None


def test_add_credits_rejects_non_positive(
    _db: str, account_id: int,
) -> None:
    """Zero and negative top-ups are rejected."""
    with pytest.raises(ValueError, match="positive"):
        add_credits(account_id, Decimal("0"), note="zero")
    with pytest.raises(ValueError, match="positive"):
        add_credits(account_id, Decimal("-5"), note="negative")


def test_debit_session_usage_is_idempotent(
    _db: str, account_id: int,
) -> None:
    """Debiting the same session twice only debits once."""
    add_credits(account_id, Decimal("10.00"), note="seed")
    first = debit_session_usage(
        account_id, "session-1", Decimal("3.00")
    )
    assert first == Decimal("7.0000")
    second = debit_session_usage(
        account_id, "session-1", Decimal("3.00")
    )
    assert second == Decimal("7.0000")
    with public_session_scope() as session:
        assert _tx_count(
            session, account_id, "session_debit", "session-1"
        ) == 1


def test_remaining_budget_clamps_at_zero(
    _db: str, account_id: int,
) -> None:
    """The spendable balance never goes negative, though the raw
    ledger balance may."""
    add_credits(account_id, Decimal("1.00"), note="seed")
    debit_session_usage(account_id, "session-over", Decimal("5.00"))
    assert get_balance(account_id) == Decimal("-4.0000")
    assert remaining_budget_usd(account_id) == Decimal("0.0000")


def test_has_credits_reflects_clamp(_db: str, account_id: int) -> None:
    """has_credits is False at exactly zero and just below zero."""
    assert has_credits(account_id) is False
    add_credits(account_id, Decimal("2.00"), note="seed")
    assert has_credits(account_id) is True
    debit_session_usage(account_id, "session-spend", Decimal("2.00"))
    assert has_credits(account_id) is False
    debit_session_usage(account_id, "session-deeper", Decimal("1.00"))
    assert has_credits(account_id) is False


def test_get_balance_unknown_account_raises(_db: str) -> None:
    """Unknown accounts raise ValueError (like quota_service)."""
    with pytest.raises(ValueError, match="not found"):
        get_balance(999_999_999)
