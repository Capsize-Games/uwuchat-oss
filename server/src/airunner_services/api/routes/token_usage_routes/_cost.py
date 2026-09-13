"""Cost computation for token usage rows."""

from __future__ import annotations

from typing import Any

from airunner_services.api.routes.token_usage_routes._pricing_fetch import (
    _ensure_model_in_cache,
)


def _compute_cost(
    row: Any, prices: dict, model_id: str
) -> float:
    """Compute estimated USD cost for one usage row.

    Falls back to an on-demand OpenRouter fetch when *model_id* is
    not in the local cache, so cost estimates are never silently zero.
    """
    p = prices.get(model_id)
    if p is None:
        p = _ensure_model_in_cache(model_id)
        prices[model_id] = p  # cache for subsequent rows
    in_price = p.get("input", 0)
    out_price = p.get("output", 0)
    cache_price = p.get("cache", 0)
    input_t = int(getattr(row, "input_tokens", 0) or 0)
    output_t = int(getattr(row, "output_tokens", 0) or 0)
    cache_t = int(getattr(row, "cache_read_tokens", 0) or 0)
    return (
        (input_t / 1_000_000) * in_price
        + (output_t / 1_000_000) * out_price
        + (cache_t / 1_000_000) * cache_price
    )
