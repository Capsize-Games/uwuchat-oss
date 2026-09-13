"""Sentry error-tracking initialization for the FastAPI server.

Gracefully degrades: when SENTRY_DSN is unset, init_sentry() is a no-op
so local development does not require a Sentry account.

Privacy constraint: never log prompts, conversation bodies, tokens,
secrets, or user content.  The before_send scrubber strips request
bodies before they leave the process.
"""

from __future__ import annotations

import os
from typing import Any, Optional

_sentry_sdk: Optional[Any] = None
_FastApiIntegration: Optional[Any] = None


def _try_import_sentry() -> None:
    """Import Sentry SDK modules, storing them as module-level optionals."""
    global _sentry_sdk, _FastApiIntegration
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        _sentry_sdk = sentry_sdk
        _FastApiIntegration = FastApiIntegration
    except ImportError:
        pass


def _scrub_before_send(event: dict, hint: dict) -> dict:
    """Strip request body — chat payloads must never reach Sentry.

    Sentry's Starlette/FastAPI integration writes captured request data
    (including the body) directly to event["request"], not to contexts.
    """
    if "request" in event:
        event["request"].pop("data", None)
    return event


def init_sentry() -> None:
    """Initialize Sentry if SENTRY_DSN is set in the environment.

    Gracefully degrades: when SENTRY_DSN is unset or the SDK is not
    installed, this is a silent no-op so local development does not
    require a Sentry account.
    """
    if _sentry_sdk is None:
        _try_import_sentry()
    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if not dsn or _sentry_sdk is None:
        return

    _sentry_sdk.init(
        dsn=dsn,
        integrations=[_FastApiIntegration()],
        environment=os.environ.get(
            "AIRUNNER_DEPLOYMENT_MODE", "development"
        ),
        traces_sample_rate=0.1,
        send_default_pii=False,
        max_request_body_size="never",
        before_send=_scrub_before_send,
    )
