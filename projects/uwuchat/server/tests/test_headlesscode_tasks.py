"""Tests for the headlesscode Celery completion handler (credit wiring).

Launch-task tests live in test_headlesscode_launch_task.py (split out
to stay under CLAUDE.md's 250-line file limit).

``finalize_session_usage`` is exercised against the real public
schema — the debit/ledger contract only means something against real
tables.
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
    get_balance,
)
from projects.uwuchat.server.models.code_credit_transaction import (
    CodeCreditTransaction,
)


@pytest.fixture()
def account_id() -> int:
    """Scratch public-schema account, removed after the test."""
    with public_session_scope() as session:
        acct = Account(
            email=f"hc-{uuid.uuid4().hex[:8]}@example.com",
            username=f"hc_{uuid.uuid4().hex[:8]}",
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


def test_finalize_session_usage_debits_by_session_id(
    _db: str, account_id: int,
) -> None:
    """The completion handler debits once per real session id."""
    from projects.uwuchat.server.tasks.headlesscode_tasks import (
        finalize_session_usage,
    )

    add_credits(account_id, Decimal("10.00"), note="seed")
    balance = finalize_session_usage(
        account_id, "hc-sess-9", Decimal("3.00"),
    )
    assert balance == Decimal("7.0000")
    # Idempotent — a second call for the same session no-ops.
    finalize_session_usage(account_id, "hc-sess-9", Decimal("3.00"))
    assert get_balance(account_id) == Decimal("7.0000")
    with public_session_scope() as session:
        rows = (
            session.query(CodeCreditTransaction)
            .filter(
                CodeCreditTransaction.kind == "session_debit",
                CodeCreditTransaction.session_id == "hc-sess-9",
            )
            .count()
        )
        assert rows == 1
