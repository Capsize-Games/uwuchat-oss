"""Billing provider interface — the contract quota code codes against.

Core and project code (``projects/<project>/server/quota_service.py``)
resolves the active provider through
:func:`airunner_services.billing.get_billing_provider` and never imports
a billing vendor SDK directly.  A deployment that sells subscriptions
installs its own implementation (the private ``uwuchat-billing``
extension installs its Stripe provider); everything else runs on
:class:`airunner_services.billing.unlimited.UnlimitedBillingProvider`.

Usage counts are *not* part of this contract: the provider answers
"what tier is this account on, and what are its caps", while the
project's quota service counts real usage from its own tables.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from airunner_services.billing.limits import TierLimits


@runtime_checkable
class BillingProvider(Protocol):
    """Subscription tier and usage-cap lookups for one account."""

    def get_subscription_tier(self, account_id: int) -> str | None:
        """Return *account_id*'s active subscription tier slug.

        ``None`` means the account holds no active subscription.
        """

    def get_period_end(self, account_id: int) -> datetime | None:
        """Return the end of *account_id*'s current billing period.

        ``None`` means there is no billing period (no subscription) —
        callers then fall back to a calendar-month window.
        """

    def get_tier_limits(self, tier: str | None) -> TierLimits:
        """Return the limits that apply to *tier*.

        Called with the slug from :meth:`get_subscription_tier`, which
        may be ``None``, and — for superuser previews — with a tier the
        account does not currently hold.
        """
