"""Billing — pluggable subscription tiers with an unlimited OSS default.

Consumers resolve the active implementation with
:func:`get_billing_provider` and code against :class:`BillingProvider`
only; the framework never imports a billing vendor SDK itself.
"""

from airunner_services.billing.limits import TierLimits
from airunner_services.billing.provider import BillingProvider
from airunner_services.billing.registry import (
    get_billing_provider,
    reset_billing_provider,
    set_billing_provider,
)
from airunner_services.billing.unlimited import UnlimitedBillingProvider

__all__ = [
    "BillingProvider",
    "TierLimits",
    "UnlimitedBillingProvider",
    "get_billing_provider",
    "reset_billing_provider",
    "set_billing_provider",
]
