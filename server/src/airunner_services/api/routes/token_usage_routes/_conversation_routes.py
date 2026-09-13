"""Per-conversation token usage admin route."""

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


@_rpc_register("GET", "/api/admin/token-usage/conversation")
async def _token_usage_conversation(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Return per-conversation cost for the current tenant's chatbot."""
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    chatbot_id_raw = body.get("chatbot_id")
    if not chatbot_id_raw:
        return {
            "status": 400,
            "body": {"error": "chatbot_id is required"},
        }
    try:
        chatbot_id = int(chatbot_id_raw)
    except (TypeError, ValueError):
        return {
            "status": 400,
            "body": {"error": "chatbot_id must be an integer"},
        }

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
                PipelineTokenUsage.chatbot_id == chatbot_id,
                PipelineTokenUsage.recorded_at >= since,
            )
            .all()
        )
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="error",
        )

    total_input = 0
    total_output = 0
    total_cost = 0.0
    skipped_calls = 0
    groups: dict = {}

    for row in rows:
        pkey = getattr(row, "pipeline_key", "?")
        model = getattr(row, "model_id", "?")
        if getattr(row, "skipped", False):
            skipped_calls += 1
        inp = int(getattr(row, "input_tokens", 0) or 0)
        out = int(getattr(row, "output_tokens", 0) or 0)
        cost = float(getattr(row, "cost_usd", 0) or 0)
        total_input += inp
        total_output += out
        total_cost += cost

        group_key = (pkey, model)
        if group_key not in groups:
            groups[group_key] = {
                "call_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
            }
        g = groups[group_key]
        g["call_count"] += 1
        g["input_tokens"] += inp
        g["output_tokens"] += out
        g["cost_usd"] += cost

    breakdown = []
    for (pkey, model), g in sorted(groups.items()):
        breakdown.append(
            {
                "pipeline_key": pkey,
                "model_id": model,
                "call_count": g["call_count"],
                "input_tokens": g["input_tokens"],
                "output_tokens": g["output_tokens"],
                "cost_usd": round(g["cost_usd"], 8),
                "pct_of_total": round(
                    (g["cost_usd"] / total_cost * 100)
                    if total_cost > 0
                    else 0,
                    1,
                ),
            }
        )

    return {
        "status": 200,
        "body": {
            "chatbot_id": chatbot_id,
            "total_cost_usd": round(total_cost, 8),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_skipped_calls": skipped_calls,
            "estimated_saved_usd": round(total_cost * 0.05, 8),
            "breakdown": breakdown,
        },
    }
