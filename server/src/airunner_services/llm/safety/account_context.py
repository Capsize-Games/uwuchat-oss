"""Thread-safe context variable for account_id propagation.

Allows tool functions and providers to access the current
request's account_id without threading it through every
function signature.
"""

from __future__ import annotations

import contextvars
from typing import Optional

_current_account_id: contextvars.ContextVar[Optional[int]] = (
    contextvars.ContextVar("current_account_id", default=None)
)


def set_current_account_id(account_id: Optional[int]) -> None:
    """Set the account_id for the current async context."""
    _current_account_id.set(account_id)


def get_current_account_id() -> Optional[int]:
    """Return the account_id for the current async context, or None."""
    return _current_account_id.get(None)


def get_account_hash() -> str:
    """Return a non-reversible hash of the current account_id.

    Suitable for the ``X-Client-Account-Hash`` header on outbound
    FastSearch requests.  Returns an empty string when no account
    context is set.
    """
    import hashlib

    aid = get_current_account_id()
    if aid is None:
        return ""
    return hashlib.sha256(str(aid).encode()).hexdigest()[:16]
