"""Tests for the pluggable billing provider registry and OSS default."""

from __future__ import annotations

import sys
import types

import pytest

from airunner_services.billing import (
    BillingProvider,
    TierLimits,
    UnlimitedBillingProvider,
    get_billing_provider,
    reset_billing_provider,
    set_billing_provider,
)
from airunner_services.billing import registry


@pytest.fixture(autouse=True)
def _reset_registry():
    """Never leak an installed provider between tests."""
    reset_billing_provider()
    yield
    reset_billing_provider()


# ---------------------------------------------------------------------------
# TierLimits
# ---------------------------------------------------------------------------


def test_uncapped_limits_are_unlimited() -> None:
    """No caps on any dimension means unlimited access."""
    limits = TierLimits()

    assert limits.is_unlimited is True
    assert limits.has_access is True
    assert limits.period_days == 30


def test_capped_limits_are_not_unlimited() -> None:
    """Any cap makes the tier finite."""
    limits = TierLimits(turns_cap=100, daily_cap=10, daily_token_cap=500)

    assert limits.is_unlimited is False


def test_no_access_limits_are_not_unlimited() -> None:
    """An account with no entitlement is not unlimited, even uncapped."""
    limits = TierLimits(has_access=False)

    assert limits.is_unlimited is False


# ---------------------------------------------------------------------------
# UnlimitedBillingProvider — the shipped default
# ---------------------------------------------------------------------------


def test_unlimited_provider_grants_uncapped_access() -> None:
    """The OSS default has no tiers and no caps."""
    provider = UnlimitedBillingProvider()

    assert provider.get_subscription_tier(1) is None
    assert provider.get_period_end(1) is None
    limits = provider.get_tier_limits(None)
    assert limits.is_unlimited is True
    assert limits.has_access is True


def test_unlimited_provider_matches_protocol() -> None:
    """The default satisfies the BillingProvider protocol."""
    assert isinstance(UnlimitedBillingProvider(), BillingProvider)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_default_provider_is_unlimited() -> None:
    """With nothing configured the unlimited provider is used."""
    assert isinstance(get_billing_provider(), UnlimitedBillingProvider)


def test_installed_provider_wins() -> None:
    """set_billing_provider() overrides the default."""
    provider = _StubProvider()
    set_billing_provider(provider)

    assert get_billing_provider() is provider


def test_reset_restores_default() -> None:
    """reset_billing_provider() drops the installed provider."""
    set_billing_provider(_StubProvider())
    reset_billing_provider()

    assert isinstance(get_billing_provider(), UnlimitedBillingProvider)


def test_configured_provider_is_discovered(monkeypatch) -> None:
    """A module named by BILLING_PROVIDER is imported and used."""
    stub = _StubProvider()
    monkeypatch.setitem(sys.modules, "billing_stub", _stub_module(stub))
    monkeypatch.setattr(registry, "_configured_path", lambda: "billing_stub")

    assert get_billing_provider() is stub


def test_missing_configured_module_falls_back(monkeypatch) -> None:
    """A module that cannot be imported must not break resolution."""
    monkeypatch.setattr(
        registry, "_configured_path", lambda: "no.such.module"
    )

    assert isinstance(get_billing_provider(), UnlimitedBillingProvider)


def test_configured_module_without_factory_falls_back(monkeypatch) -> None:
    """A module lacking the factory falls back to the default."""
    module = types.ModuleType("billing_no_factory")
    monkeypatch.setitem(sys.modules, "billing_no_factory", module)
    monkeypatch.setattr(
        registry, "_configured_path", lambda: "billing_no_factory"
    )

    assert isinstance(get_billing_provider(), UnlimitedBillingProvider)


def test_configured_path_reads_setting(monkeypatch) -> None:
    """The dotted path comes from the BILLING_PROVIDER setting."""
    from airunner_services.conf import settings

    monkeypatch.setattr(
        settings, "get", lambda name, default=None: "pkg.billing"
    )

    assert registry._configured_path() == "pkg.billing"


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class _StubProvider:
    """Minimal BillingProvider implementation for registry tests."""

    def get_subscription_tier(self, account_id: int) -> str | None:
        """Return a fixed tier slug."""
        del account_id
        return "stub"

    def get_period_end(self, account_id: int):
        """Return no billing period."""
        del account_id
        return None

    def get_tier_limits(self, tier: str | None) -> TierLimits:
        """Return finite limits for every tier."""
        del tier
        return TierLimits(turns_cap=10, daily_cap=1, daily_token_cap=100)


def _stub_module(provider: _StubProvider) -> types.ModuleType:
    """Build a module exposing a get_billing_provider() factory."""
    module = types.ModuleType("billing_stub")
    module.get_billing_provider = lambda: provider
    return module
