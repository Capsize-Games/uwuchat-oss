"""RPC handlers: privacy settings."""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.api.routes.events import (
    _rpc_error_response,
    _rpc_register,
)
from airunner_services.api.ws_tenant import resolve_ws_tenant

logger = logging.getLogger(__name__)


def _privacy_auth(kw: dict) -> int | None:
    """Resolve and return the account_id from the WS context.

    Returns None when the socket is unauthenticated — callers must
    reject the request with a 401-equivalent response.
    """
    ws = kw.get("ws")
    if ws is None:
        return None
    _tenant, account_id = resolve_ws_tenant(ws)
    return account_id


@_rpc_register("GET", "/api/v1/settings/privacy")
async def _rpc_privacy_get(body: dict, **kwargs: Any) -> dict[str, Any]:
    """Return privacy settings."""
    account_id = _privacy_auth(kwargs)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    try:
        from airunner_services.database.models import PrivacySetting

        records = PrivacySetting.objects.query().all()
        services = {r.service_name: bool(r.enabled) for r in records}
        return {"status": 200, "body": {"services": services}}
    except Exception:
        return {"status": 200, "body": {"services": {}}}


@_rpc_register("PUT", "/api/v1/settings/privacy")
async def _rpc_privacy_update(body: dict, **kwargs: Any) -> dict[str, Any]:
    """Update privacy settings."""
    account_id = _privacy_auth(kwargs)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    services: dict = body.get("services", {})
    try:
        from airunner_services.database.models import PrivacySetting

        with PrivacySetting.objects.transaction() as tx:
            for name, enabled in services.items():
                record = (
                    tx.query(PrivacySetting)
                    .filter(
                        PrivacySetting.service_name == name,
                    )
                    .first()
                )
                if record:
                    record.enabled = bool(enabled)
                else:
                    tx.add(
                        PrivacySetting(
                            service_name=name,
                            enabled=bool(enabled),
                        )
                    )
        return {"status": 200, "body": {"services": services}}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="privacy update failed",
        )
