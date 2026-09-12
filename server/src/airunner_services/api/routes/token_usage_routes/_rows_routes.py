"""Paginated usage rows admin route."""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.api.routes.events_rpc import (
    _rpc_error_response,
    _rpc_register,
)
from airunner_services.api.routes.token_usage_routes._superuser import (
    _require_superuser,
)

logger = logging.getLogger(__name__)


@_rpc_register("GET", "/api/admin/token-usage/rows")
async def _token_usage_rows(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Return paginated PipelineTokenUsage rows for drill-down.

    Query params (in *body*):
      - days (int, default 30): lookback window
      - limit (int, default 50, max 200): rows per page
      - offset (int, default 0): page offset
      - account_id (int, optional): filter by account
      - pipeline_key (str, optional): filter by pipeline key
      - model_id (str, optional): filter by model
    """
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    days = int(body.get("days", 30))
    limit = min(int(body.get("limit", 50)), 200)
    offset = max(int(body.get("offset", 0)), 0)
    from datetime import datetime, timedelta

    since = datetime.utcnow() - timedelta(days=days)

    try:
        from airunner_services.database.models.pipeline_token_usage import (
            PipelineTokenUsage,
        )

        q = (
            PipelineTokenUsage.objects.query()
            .filter(PipelineTokenUsage.recorded_at >= since)
        )
        acct = body.get("account_id")
        if acct is not None:
            q = q.filter(PipelineTokenUsage.account_id == int(acct))
        pkey = body.get("pipeline_key")
        if pkey:
            q = q.filter(PipelineTokenUsage.pipeline_key == pkey)
        mid = body.get("model_id")
        if mid:
            q = q.filter(PipelineTokenUsage.model_id == mid)
        total = q.count()
        rows = (
            q.order_by(PipelineTokenUsage.recorded_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="error",
        )

    items = []
    for row in rows:
        items.append(
            {
                "id": getattr(row, "id", None),
                "pipeline_key": getattr(row, "pipeline_key", ""),
                "model_id": getattr(row, "model_id", ""),
                "account_id": getattr(row, "account_id", None),
                "tenant_key": getattr(row, "tenant_key", None),
                "chatbot_id": getattr(row, "chatbot_id", None),
                "call_chain_id": getattr(row, "call_chain_id", None),
                "input_tokens": int(
                    getattr(row, "input_tokens", 0) or 0
                ),
                "output_tokens": int(
                    getattr(row, "output_tokens", 0) or 0
                ),
                "cache_read_tokens": int(
                    getattr(row, "cache_read_tokens", 0) or 0
                ),
                "cost_usd": (
                    float(getattr(row, "cost_usd", None))
                    if getattr(row, "cost_usd", None) is not None
                    else None
                ),
                "tier_name": getattr(row, "tier_name", None),
                "skipped": bool(getattr(row, "skipped", False)),
                "prompt_char_count": getattr(
                    row, "prompt_char_count", None
                ),
                "response_char_count": getattr(
                    row, "response_char_count", None
                ),
                "recorded_at": (
                    getattr(row, "recorded_at", None).isoformat()
                    if getattr(row, "recorded_at", None)
                    else None
                ),
            }
        )

    return {
        "status": 200,
        "body": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "rows": items,
        },
    }
