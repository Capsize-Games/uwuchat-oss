"""Billing provider selection — pluggable, with an OSS default.

Resolution order:

1. a provider installed with :func:`set_billing_provider` — what an
   extension's ``ready()`` hook does, mirroring how the object-storage
   extension installs its S3 backend;
2. the dotted module path in the ``BILLING_PROVIDER`` setting
   (``AIRUNNER_BILLING_PROVIDER``), for a self-hoster who drops in
   their own implementation without forking ``quota_service.py``; the
   module must expose a ``get_billing_provider()`` factory.  A module
   that cannot be imported falls back rather than breaking boot;
3. :class:`UnlimitedBillingProvider`.
"""

from __future__ import annotations

import importlib
import logging

from airunner_services.billing.provider import BillingProvider
from airunner_services.billing.unlimited import UnlimitedBillingProvider

logger = logging.getLogger(__name__)

_provider: BillingProvider | None = None


def get_billing_provider() -> BillingProvider:
    """Return the active billing provider."""
    global _provider
    if _provider is None:
        configured = _resolve_configured_provider()
        _provider = configured or UnlimitedBillingProvider()
    return _provider


def set_billing_provider(provider: BillingProvider) -> None:
    """Install *provider* as the process-wide billing implementation."""
    global _provider
    _provider = provider


def reset_billing_provider() -> None:
    """Drop any installed provider so the default is rebuilt."""
    global _provider
    _provider = None


def _configured_path() -> str:
    """Return the dotted path in the BILLING_PROVIDER setting, if any."""
    from airunner_services.conf import settings

    return str(settings.get("BILLING_PROVIDER", "") or "").strip()


def _resolve_configured_provider() -> BillingProvider | None:
    """Return the provider named by the BILLING_PROVIDER setting."""
    dotted = _configured_path()
    if not dotted:
        return None
    try:
        module = importlib.import_module(dotted)
    except ImportError:
        logger.warning(
            "BILLING_PROVIDER '%s' could not be imported — falling back "
            "to the unlimited billing provider",
            dotted,
        )
        return None
    factory = getattr(module, "get_billing_provider", None)
    if not callable(factory):
        logger.warning(
            "BILLING_PROVIDER '%s' has no get_billing_provider() factory "
            "— falling back to the unlimited billing provider",
            dotted,
        )
        return None
    return factory()
