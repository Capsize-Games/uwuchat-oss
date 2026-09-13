"""Pricing health diagnostic admin route."""

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


@_rpc_register("GET", "/api/admin/token-usage/pricing-health")
async def _pricing_health(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Diagnostic: check pricing health for models in use.

    Returns a list of models referenced by pipeline_token_usage rows,
    with their cached pricing and any issues detected (zero_price,
    not_in_cache, or null).
    """
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    try:
        from airunner_services.database.models.pipeline_token_usage import (
            PipelineTokenUsage,
        )

        rows = PipelineTokenUsage.objects.query().all()
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="error",
        )

    model_ids: set = set()
    for row in rows:
        mid = getattr(row, "model_id", None)
        if mid:
            model_ids.add(mid)

    results = []
    for mid in sorted(model_ids):
        entry = {
            "model_id": mid,
            "in_cache": False,
            "input_price": 0.0,
            "output_price": 0.0,
            "issue": "not_in_cache",
        }
        try:
            from airunner_services.database.models.openrouter_model import (
                OpenRouterModel,
            )

            orow = (
                OpenRouterModel.objects.query()
                .filter(OpenRouterModel.model_id == mid)
                .first()
            )
            if orow is not None:
                entry["in_cache"] = True
                entry["input_price"] = float(
                    getattr(orow, "input_price_per_mtok", 0) or 0
                )
                entry["output_price"] = float(
                    getattr(orow, "output_price_per_mtok", 0) or 0
                )
                if entry["input_price"] == 0 and entry[
                    "output_price"
                ] == 0:
                    entry["issue"] = "zero_price"
                else:
                    entry["issue"] = None
        except Exception:
            pass
        results.append(entry)

    return {
        "status": 200,
        "body": {
            "models_in_use": len(model_ids),
            "models_missing_pricing": sum(
                1 for r in results if r["issue"] is not None
            ),
            "entries": results,
        },
    }
