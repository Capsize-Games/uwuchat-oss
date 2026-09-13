"""Account listing admin route for token usage."""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.api.routes.events_rpc import (
    _rpc_error_response,
    _rpc_register,
)
from airunner_services.api.routes.token_usage_routes._aggregation import (
    _accounts_with_email,
)
from airunner_services.api.routes.token_usage_routes._superuser import (
    _require_superuser,
)

logger = logging.getLogger(__name__)


@_rpc_register("GET", "/api/admin/token-usage/accounts")
async def _token_usage_accounts(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Return distinct accounts with usage rows in the lookback window.

    Backs the Account filter dropdown in the cost tracking admin panel.
    """
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    days = int(body.get("days", 30))
    from datetime import datetime, timedelta

    since = datetime.utcnow() - timedelta(days=days)

    try:
        from airunner_services.database.models.pipeline_token_usage import (
            PipelineTokenUsage,
        )

        rows = (
            PipelineTokenUsage.objects.query()
            .filter(
                PipelineTokenUsage.recorded_at >= since,
                PipelineTokenUsage.account_id.isnot(None),
            )
            .all()
        )
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="error",
        )

    account_ids = sorted(
        {int(getattr(r, "account_id")) for r in rows}
    )
    return {
        "status": 200,
        "body": {"accounts": _accounts_with_email(account_ids)},
    }
