"""Tests for the headlesscode usage reconciler.

Driven entirely by checked-in fixture JSONL/live.json files — no real
headlesscode process is needed, which is the whole point of the stable
file-format contract this task consumes.
"""

from __future__ import annotations

import json
import shutil
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from airunner_services.contract_enums import ModelService
from airunner_services.database.session import public_session_scope
from extensions.auth.server.models import Account
from projects.uwuchat.server.code_credits_reconciler import (
    reconcile_session_usage,
)
from projects.uwuchat.server.code_credits_service import (
    add_credits,
    get_balance,
)

FIXTURES = Path(__file__).parent / "fixtures" / "code_credits"


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


@pytest.fixture()
def usage_dir(tmp_path: Path) -> Path:
    """A per-test workspace root, seeded from the checked-in fixtures.

    The reconciler takes a workspace *root* and appends
    ``.headlesscode/usage/`` itself, so this returns ``tmp_path``.
    """
    usage = tmp_path / ".headlesscode" / "usage"
    usage.mkdir(parents=True)
    for fixture in FIXTURES.iterdir():
        shutil.copy(fixture, usage / fixture.name)
    return tmp_path


def _seed(account_id: int, amount: str) -> None:
    add_credits(account_id, Decimal(amount), note="test seed")


def test_missing_file_returns_balance_unchanged(
    _db: str, account_id: int, usage_dir: Path
) -> None:
    """A session with no usage files yet must not error or debit."""
    _seed(account_id, "5.00")
    balance = reconcile_session_usage(
        account_id, str(usage_dir), "no-such-session"
    )
    assert balance == Decimal("5.0000")


def test_live_delta_across_repeated_polls(
    _db: str, account_id: int, usage_dir: Path
) -> None:
    """Mid-session polls debit only the delta since the last poll."""
    _seed(account_id, "1.00")
    first = reconcile_session_usage(account_id, str(usage_dir), "live_mid")
    assert first == Decimal("0.9950")
    # The session progresses: overwrite the live snapshot with a later,
    # higher-cost snapshot (same sessionId, same lookup key).
    record = json.loads(
        (FIXTURES / "live_final.live.json").read_text(encoding="utf-8")
    )
    record["sessionId"] = "live_mid"
    (usage_dir / ".headlesscode" / "usage" / "live_mid.live.json").write_text(
        json.dumps(record), encoding="utf-8"
    )
    second = reconcile_session_usage(account_id, str(usage_dir), "live_mid")
    assert second == Decimal("0.9920")
    # Total debited across both polls is 0.008, not 0.005 + 0.008.
    assert get_balance(account_id) == Decimal("0.9920")


def test_finalized_record_debits_once(
    _db: str, account_id: int, usage_dir: Path
) -> None:
    """A finalized .jsonl record is debited once, not on every poll."""
    _seed(account_id, "1.00")
    first = reconcile_session_usage(account_id, str(usage_dir), "finalized")
    assert first == Decimal("0.9891")
    second = reconcile_session_usage(account_id, str(usage_dir), "finalized")
    assert second == Decimal("0.9891")
    assert get_balance(account_id) == Decimal("0.9891")


def test_malformed_jsonl_is_skipped_not_fatal(
    _db: str, account_id: int, usage_dir: Path
) -> None:
    """Garbage lines and non-string sessionIds are skipped; the valid
    line still debits. The reconciler must never crash on bad data."""
    _seed(account_id, "1.00")
    balance = reconcile_session_usage(account_id, str(usage_dir), "malformed")
    # Only the third (valid) line debited: 1.00 - 0.0025.
    assert balance == Decimal("0.9975")


def test_jsonl_wins_over_live_snapshot(
    _db: str, account_id: int, usage_dir: Path
) -> None:
    """When both files exist, the finalized .jsonl value is authoritative
    (headlesscode's own precedence) and stays a single debit."""
    _seed(account_id, "1.00")
    balance = reconcile_session_usage(account_id, str(usage_dir), "both")
    # Finalized 0.0111 wins over the stale live 0.003.
    assert balance == Decimal("0.9889")
    again = reconcile_session_usage(account_id, str(usage_dir), "both")
    assert again == Decimal("0.9889")
    assert get_balance(account_id) == Decimal("0.9889")
