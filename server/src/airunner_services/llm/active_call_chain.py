"""Context variable for the current call_chain_id.

Set by the DIALOGUE workflow before execution and read by background
LLM callers (tools, summarizers, etc.) so every pipeline stage is
attributed to the same call chain.
"""

from __future__ import annotations

from contextvars import ContextVar

_active_call_chain_id: ContextVar[str | None] = ContextVar(
    "active_call_chain_id", default=None
)


def set_active_call_chain(call_chain_id: str) -> None:
    """Set the active call_chain_id for the current async context."""
    _active_call_chain_id.set(call_chain_id)


def get_active_call_chain() -> str | None:
    """Return the active call_chain_id, or None if not set."""
    return _active_call_chain_id.get()
