"""Unlimited billing provider — the shipped OSS default."""

from __future__ import annotations

from datetime import datetime

from airunner_services.billing.limits import TierLimits


class UnlimitedBillingProvider:
    """Every account has unlimited access — no tiers, no caps.

    This is the default for self-hosted UwUChat: a fresh account can
    chat with no billing extension present at all.  It is a deliberate
    product decision, not a config-driven cap, so there is nothing to
    configure here.

    A plain class rather than an explicit ``BillingProvider`` subclass:
    the protocol is structural, so there is no base class to inherit
    and the default stays free of vendor coupling.
    """

    def get_subscription_tier(self, account_id: int) -> str | None:
        """Return ``None`` — self-hosted deployments have no tiers."""
        del account_id
        return None

    def get_period_end(self, account_id: int) -> datetime | None:
        """Return ``None`` — there is no billing period."""
        del account_id
        return None

    def get_tier_limits(self, tier: str | None) -> TierLimits:
        """Return uncapped limits for every tier."""
        del tier
        return TierLimits()
