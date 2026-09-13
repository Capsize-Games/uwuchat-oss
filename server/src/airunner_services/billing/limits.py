"""Tier limits — the cap shape shared by every billing provider."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TierLimits:
    """Usage caps that apply to one account's billing tier.

    A ``None`` cap means "no cap" for that dimension.  That is how the
    shipped :class:`UnlimitedBillingProvider` expresses the OSS
    default: no tiers, no caps.

    ``period_days`` is the length of the tier's billing period, used to
    derive the start of the current usage window from the period end.

    ``has_access`` False means the account holds no entitlement at all
    (no active subscription): callers must block it outright.  That is
    provider *policy*, which is why it lives here rather than in the
    project's quota service.
    """

    turns_cap: int | None = None
    daily_cap: int | None = None
    daily_token_cap: int | None = None
    period_days: int = 30
    has_access: bool = True

    @property
    def is_unlimited(self) -> bool:
        """Return True when the account may use the service uncapped."""
        if not self.has_access:
            return False
        return (
            self.turns_cap is None
            and self.daily_cap is None
            and self.daily_token_cap is None
        )
