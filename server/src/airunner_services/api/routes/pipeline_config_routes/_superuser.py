"""Superuser guard shared by pipeline-config admin routes."""

from __future__ import annotations

from typing import Any


def _require_superuser(ws: Any) -> int | None:
    """Return the authenticated account_id if superuser, or None."""
    try:
        from airunner_services.api.ws_tenant import resolve_ws_tenant

        _tenant, account_id = resolve_ws_tenant(ws)
        if account_id is None:
            return None
        from extensions.auth.server.models import Account

        acct = Account.objects.get(account_id)
        if acct is None or not getattr(acct, "is_superuser", False):
            return None
        return account_id
    except Exception:
        return None
