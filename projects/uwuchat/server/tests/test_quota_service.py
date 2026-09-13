"""Unit tests for UwUchat quota service.

Tests are mock-only — no real database or billing provider calls are
made; tier data comes from a stand-in provider injected via
``quota_service.get_billing_provider``.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from airunner_services.billing import TierLimits
from projects.uwuchat.server.quota_service import (
    QuotaResult,
    get_quota,
    is_over_daily_token_limit,
    is_over_quota,
)

_TARGET = "projects.uwuchat.server.quota_service"


class _FakeProvider:
    """Tiered stand-in for a paid billing provider."""

    def __init__(
        self,
        tier: str | None = "companion",
        *,
        turns_cap: int | None = 21_000,
        daily_cap: int | None = 700,
        daily_token_cap: int | None = 6_000_000,
        period_days: int = 30,
        period_end: datetime | None = None,
        has_access: bool = True,
    ) -> None:
        self.tier = tier
        self.period_end = period_end
        self.limits = TierLimits(
            turns_cap=turns_cap,
            daily_cap=daily_cap,
            daily_token_cap=daily_token_cap,
            period_days=period_days,
            has_access=has_access,
        )

    def get_subscription_tier(self, account_id: int) -> str | None:
        """Return the tier held by every account."""
        del account_id
        return self.tier

    def get_period_end(self, account_id: int) -> datetime | None:
        """Return the configured billing period end."""
        del account_id
        return self.period_end

    def get_tier_limits(self, tier: str | None) -> TierLimits:
        """Return the configured limits regardless of *tier*."""
        del tier
        return self.limits


def _mock_account(
    tier: str | None = "companion",
    is_superuser: bool = False,
    period_end: datetime | None = None,
    tenant_schema: str = "tenant_test",
) -> MagicMock:
    """Build a mock Account object."""
    acct = MagicMock()
    acct.is_superuser = is_superuser
    acct.tenant_schema = tenant_schema
    return acct


def _mock_session(account: MagicMock) -> MagicMock:
    """Build a mock session that returns *account* from get()."""
    session = MagicMock()
    session.get.return_value = account
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


@contextmanager
def _quota_env(account: MagicMock, provider=None):
    """Patch the session scope and, when given, the billing provider.

    Yields the mock session.  Without *provider* the real registry is
    left in place, so the shipped unlimited default is exercised.
    """
    session = _mock_session(account)
    with patch(f"{_TARGET}.public_session_scope", return_value=session):
        if provider is None:
            yield session
            return
        with patch(
            f"{_TARGET}.get_billing_provider", return_value=provider
        ):
            yield session


# ---------------------------------------------------------------------------
# Basic quota retrieval
# ---------------------------------------------------------------------------


def test_get_quota_returns_structure() -> None:
    """get_quota returns a QuotaResult with expected keys."""
    with _quota_env(_mock_account(), _FakeProvider()) as sess:
        sess.execute.return_value.scalar_one.return_value = 0
        result = get_quota(42)

    assert isinstance(result, dict)
    assert "turns_used" in result
    assert "turns_cap" in result
    assert "tier" in result
    assert result["tier"] == "companion"


def test_get_quota_superuser_is_unlimited() -> None:
    """Superuser accounts are marked as unlimited."""
    with _quota_env(_mock_account(is_superuser=True), _FakeProvider()) as sess:
        sess.execute.return_value.scalar_one.return_value = 0
        result = get_quota(42)

    assert result["is_unlimited"] is True
    assert result["turns_cap"] is None
    assert result["daily_cap"] is None


def test_get_quota_regular_user_has_caps() -> None:
    """A regular (non-superuser) tier has finite caps."""
    acct = _mock_account(tier="companion", is_superuser=False)
    with _quota_env(acct, _FakeProvider()) as sess:
        sess.execute.return_value.scalar_one.return_value = 0
        result = get_quota(42)

    assert result["is_unlimited"] is False
    assert result["has_access"] is True
    assert result["turns_cap"] == 21_000
    assert result["daily_cap"] == 700


def test_get_quota_account_not_found_raises() -> None:
    """get_quota raises ValueError when account_id does not exist."""
    with _quota_env(None):
        with pytest.raises(ValueError, match="not found"):
            get_quota(999)


# ---------------------------------------------------------------------------
# Default (OSS) provider
# ---------------------------------------------------------------------------


def test_default_provider_is_unlimited() -> None:
    """With no provider installed every account is unlimited."""
    with _quota_env(_mock_account(tier=None)) as sess:
        sess.execute.return_value.scalar_one.return_value = 0
        result = get_quota(42)

    assert result["is_unlimited"] is True
    assert result["has_access"] is True
    assert result["turns_cap"] is None
    assert result["daily_cap"] is None


def test_default_provider_never_over_quota() -> None:
    """The unlimited default blocks nobody, whatever the usage."""
    with _quota_env(_mock_account(tier=None)) as sess:
        sess.execute.return_value.scalar_one.side_effect = [999_999, 999_999]
        assert is_over_quota(42) is False


def test_no_access_provider_blocks_account() -> None:
    """A provider reporting no entitlement blocks the account."""
    acct = _mock_account(tier=None, is_superuser=False)
    provider = _FakeProvider(
        tier=None, turns_cap=None, daily_cap=None, has_access=False
    )
    with _quota_env(acct, provider) as sess:
        sess.execute.return_value.scalar_one.return_value = 0
        result = get_quota(42)

    assert result["has_access"] is False
    assert result["is_unlimited"] is False

    with _quota_env(acct, provider) as sess:
        sess.execute.return_value.scalar_one.return_value = 0
        assert is_over_quota(42) is True


def test_capped_provider_blocks_at_grace_threshold() -> None:
    """Usage past the grace buffer of a turn cap is over quota."""
    acct = _mock_account(is_superuser=False)
    provider = _FakeProvider(turns_cap=100, daily_cap=100)
    with _quota_env(acct, provider) as sess:
        sess.execute.return_value.scalar_one.side_effect = [109, 1]
        assert is_over_quota(42) is False
    with _quota_env(acct, provider) as sess:
        sess.execute.return_value.scalar_one.side_effect = [110, 1]
        assert is_over_quota(42) is True


# ---------------------------------------------------------------------------
# preview_tier (superuser only)
# ---------------------------------------------------------------------------


def test_preview_tier_overrides_tier_for_superuser() -> None:
    """preview_tier changes caps without making the user unlimited."""
    acct = _mock_account(is_superuser=True, tier="companion")
    with _quota_env(acct, _FakeProvider(tier="devoted")) as sess:
        sess.execute.return_value.scalar_one.return_value = 0
        result = get_quota(42, preview_tier="devoted")

    assert result["tier"] == "devoted"
    assert result["is_unlimited"] is False


# ---------------------------------------------------------------------------
# Turn counting
# ---------------------------------------------------------------------------


def test_turns_used_is_counted() -> None:
    """get_quota reports the number of turns used."""
    with _quota_env(_mock_account(), _FakeProvider()) as sess:
        sess.execute.return_value.scalar_one.side_effect = [12, 3]
        result = get_quota(42)

    assert result["turns_used"] == 12
    assert result["turns_used_today"] == 3


# ---------------------------------------------------------------------------
# Period dates
# ---------------------------------------------------------------------------


def test_period_start_from_period_end() -> None:
    """When a period end is reported, period_start is computed."""
    period_end = datetime(2026, 7, 20, 12, 0, 0)
    provider = _FakeProvider(period_end=period_end)
    with _quota_env(_mock_account(period_end=period_end), provider) as sess:
        sess.execute.return_value.scalar_one.return_value = 0
        result = get_quota(42)

    assert result["period_end"] == period_end.isoformat()
    assert result["period_start"] < result["period_end"]
    assert result["period_days_remaining"] is not None


def test_period_defaults_to_calendar_month() -> None:
    """With no billing period the window is the current calendar month."""
    with _quota_env(_mock_account(period_end=None)) as sess:
        sess.execute.return_value.scalar_one.return_value = 0
        result = get_quota(42)

    assert result["period_end"] is None
    assert result["period_start"].endswith("-01T00:00:00")


# ---------------------------------------------------------------------------
# is_over_daily_token_limit — fail-closed on query error
# ---------------------------------------------------------------------------


def test_daily_token_limit_query_error_fails_closed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the daily token query raises, the method returns True
    (blocks spend) rather than silently allowing it."""
    caplog.set_level(logging.ERROR)

    with _quota_env(_mock_account(), _FakeProvider()) as sess:
        sess.execute.side_effect = RuntimeError("DB connection lost")
        result = is_over_daily_token_limit(42)

    assert result is True, (
        "Query error must fail closed (block spend), "
        "not silently allow it"
    )
    # Assert the exception was logged.
    assert any(
        "Daily token limit check failed" in r.message
        for r in caplog.records
    ), "Exception must be logged for observability"


def test_daily_token_limit_under_cap_passes() -> None:
    """Usage below the tier's token cap is allowed."""
    with _quota_env(_mock_account(), _FakeProvider()) as sess:
        sess.execute.return_value.scalar_one.return_value = 10
        assert is_over_daily_token_limit(42) is False


def test_daily_token_limit_at_cap_blocks() -> None:
    """Usage at the tier's token cap is blocked."""
    with _quota_env(_mock_account(), _FakeProvider()) as sess:
        sess.execute.return_value.scalar_one.return_value = 6_000_000
        assert is_over_daily_token_limit(42) is True


def test_daily_token_limit_unlimited_without_provider() -> None:
    """The unlimited default has no token ceiling."""
    with _quota_env(_mock_account(tier=None)) as sess:
        sess.execute.return_value.scalar_one.return_value = 10**9
        assert is_over_daily_token_limit(42) is False


def test_daily_token_limit_superuser_is_exempt() -> None:
    """Superusers are never blocked by the daily token ceiling."""
    with _quota_env(_mock_account(is_superuser=True), _FakeProvider()) as sess:
        sess.execute.return_value.scalar_one.return_value = 10**9
        assert is_over_daily_token_limit(42) is False


def test_quota_result_shape_is_unchanged_for_clients() -> None:
    """The response keeps every key the client reads."""
    expected = {
        "turns_used",
        "turns_used_today",
        "turns_cap",
        "daily_cap",
        "pct",
        "pct_today",
        "period_start",
        "period_end",
        "period_days_remaining",
        "tier",
        "is_unlimited",
    }
    assert expected.issubset(QuotaResult.__annotations__)
