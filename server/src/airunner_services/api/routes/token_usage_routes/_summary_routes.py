"""Token usage summary and per-customer admin routes."""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.api.routes.events_rpc import (
    _rpc_error_response,
    _rpc_register,
)
from airunner_services.api.routes.token_usage_routes._aggregation import (
    _per_account_request_stats,
    _tier_breakdown,
)
from airunner_services.api.routes.token_usage_routes._superuser import (
    _require_superuser,
)

logger = logging.getLogger(__name__)


@_rpc_register("GET", "/api/admin/token-usage/summary")
async def _token_usage_summary(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Return token usage summary grouped by (pipeline_key, model_id)."""
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
            .filter(PipelineTokenUsage.recorded_at >= since)
            .all()
        )
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="error",
        )

    groups: dict = {}
    for row in rows:
        key = getattr(row, "pipeline_key", "?")
        model = getattr(row, "model_id", "?")
        group_key = (key, model)
        if group_key not in groups:
            groups[group_key] = {
                "count": 0,
                "priced_count": 0,
                "input": 0,
                "output": 0,
                "cache": 0,
                "cost": 0.0,
            }
        g = groups[group_key]
        g["count"] += 1
        g["input"] += int(getattr(row, "input_tokens", 0) or 0)
        g["output"] += int(getattr(row, "output_tokens", 0) or 0)
        g["cache"] += int(
            getattr(row, "cache_read_tokens", 0) or 0
        )
        cost = getattr(row, "cost_usd", None)
        if cost is not None:
            g["priced_count"] += 1
            g["cost"] += float(cost)

    result = []
    for (pkey, model), g in sorted(groups.items()):
        item = {
            "pipeline_key": pkey,
            "model_id": model,
            "call_count": g["count"],
            "priced_call_count": g["priced_count"],
            "total_input_tokens": g["input"],
            "total_output_tokens": g["output"],
            "total_cache_read_tokens": g["cache"],
            "cost_usd": round(g["cost"], 8),
        }

        # DIALOGUE tier breakdown
        if pkey == "DIALOGUE":
            item["tier_breakdown"] = _tier_breakdown(
                rows, pkey
            )

        result.append(item)

    return {"status": 200, "body": result}


@_rpc_register("GET", "/api/admin/token-usage/per-customer")
async def _token_usage_per_customer(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Return per-account request counts and cost.

    A "request" is one distinct call_chain_id — a single user-initiated
    turn, which may fan out into several PipelineTokenUsage rows
    (dialogue, tool classification, knowledge, mood, ...). Accounts are
    billed per request, not per raw LLM call, so this is the unit that
    matters here — not PipelineTokenUsage.call_count.

    Cost tracking only started partway through some days (see
    pricing-health), so a request's cost is only trustworthy when every
    row in its chain has a priced cost_usd. Requests with any unpriced
    row are still counted in total_requests but excluded from
    total_cost_usd / avg_cost_per_request_usd to avoid understating cost.
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
                PipelineTokenUsage.call_chain_id.isnot(None),
            )
            .all()
        )
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="error",
        )

    tenants = {
        r.tenant_key for r in rows if getattr(r, "tenant_key", None)
    }
    accounts = _per_account_request_stats(rows)

    return {
        "status": 200,
        "body": {
            "days": days,
            "distinct_tenants": max(len(tenants), 1),
            "accounts": accounts,
        },
    }
