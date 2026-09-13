"""Admin pricing-health HTTP endpoints (superuser-gated).

Exposes model pricing status as an ordinary HTTP API so it can be
called from a browser or admin UI without going through WebSocket RPC.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

router = APIRouter()
_log = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Superuser guard
# ------------------------------------------------------------------


def _resolve_superuser_dep():
    """Return a dependency that requires superuser or loopback."""
    # nosemgrep: auth-import-error-fallback (see round-7 review)
    try:
        from extensions.auth.server.dependencies import (
            require_superuser,
        )

        return require_superuser
    except ImportError:
        pass

    async def _loopback_only(request: Request) -> int:
        from airunner_services.api.server import (
            is_loopback_request,
        )

        if not is_loopback_request(request):
            raise HTTPException(
                status_code=403, detail="Admin access required"
            )
        return 0

    return _loopback_only


_superuser_dep = _resolve_superuser_dep()


# ------------------------------------------------------------------
# GET /pricing-health
# ------------------------------------------------------------------


@router.get("/pricing-health")
async def pricing_health(
    req: Request,
    _account_id: int = Depends(_superuser_dep),
) -> dict:
    """Return pricing status for every model ever used in the pipeline.

    Queries *pipeline_token_usage* for distinct model IDs, then looks
    each one up in *openrouter_model*.  Returns a list with status:
    ``"OK"``, ``"$0"``, or ``"NOT IN CATALOG"``.
    """
    try:
        from airunner_services.database.models.pipeline_token_usage import (
            PipelineTokenUsage,
        )

        rows = PipelineTokenUsage.objects.query().all()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query pipeline_token_usage: {exc}",
        )

    model_ids: set = set()
    token_counts: dict = {}
    pipeline_keys: dict = {}
    for row in rows:
        mid = getattr(row, "model_id", None)
        if not mid:
            continue
        model_ids.add(mid)
        inp = int(getattr(row, "input_tokens", 0) or 0)
        out = int(getattr(row, "output_tokens", 0) or 0)
        if mid not in token_counts:
            token_counts[mid] = {"input": 0, "output": 0}
            pipeline_keys[mid] = set()
        token_counts[mid]["input"] += inp
        token_counts[mid]["output"] += out
        pk = getattr(row, "pipeline_key", "")
        if pk:
            pipeline_keys[mid].add(pk)

    results = []
    for mid in sorted(model_ids):
        entry = _lookup_model(mid)
        entry["total_input_tokens"] = token_counts.get(mid, {}).get(
            "input", 0
        )
        entry["total_output_tokens"] = token_counts.get(mid, {}).get(
            "output", 0
        )
        entry["pipeline_keys"] = sorted(pipeline_keys.get(mid, set()))
        results.append(entry)

    return {
        "models_in_use": len(model_ids),
        "models_missing_pricing": sum(
            1 for r in results if r["status"] != "OK"
        ),
        "entries": results,
    }


# ------------------------------------------------------------------
# POST /pricing-health/fix
# ------------------------------------------------------------------


@router.post("/pricing-health/fix")
async def pricing_health_fix(
    req: Request,
    _account_id: int = Depends(_superuser_dep),
) -> dict:
    """Fetch the full OpenRouter catalog and upsert all models.

    This resets pricing for every model cached in *openrouter_model*
    and fixes any zero-price placeholders left behind by failed
    earlier fetches.
    """
    try:
        from airunner_services.llm.openrouter_catalog import (
            sync_catalog,
        )

        count = sync_catalog()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Catalog sync failed: {exc}",
        )

    if count == 0:
        raise HTTPException(
            status_code=502,
            detail="Catalog sync returned 0 models — "
            "check OpenRouter connectivity",
        )

    # Clear fetch-failed set so previously-blacklisted models get a
    # fresh lookup on the next cost computation.
    try:
        from airunner_services.api.routes.token_usage_routes import (
            _fetch_failed,
            _fetch_in_flight,
        )

        _fetch_failed.clear()
        _fetch_in_flight.clear()
    except ImportError:
        pass

    # Re-run the health check so the caller gets the updated status
    # in a single response.
    return await pricing_health(req)


def _lookup_model(model_id: str) -> dict[str, Any]:
    """Return pricing status for one model ID."""
    entry: dict[str, Any] = {
        "model_id": model_id,
        "input_price_per_mtok": 0.0,
        "output_price_per_mtok": 0.0,
        "cache_read_per_mtok": 0.0,
        "status": "NOT IN CATALOG",
    }
    try:
        from airunner_services.database.models.openrouter_model import (
            OpenRouterModel,
        )

        orow = (
            OpenRouterModel.objects.query()
            .filter(OpenRouterModel.model_id == model_id)
            .first()
        )
        if orow is not None:
            inp = float(
                getattr(orow, "input_price_per_mtok", 0) or 0
            )
            out = float(
                getattr(orow, "output_price_per_mtok", 0) or 0
            )
            entry["input_price_per_mtok"] = inp
            entry["output_price_per_mtok"] = out
            entry["cache_read_per_mtok"] = float(
                getattr(orow, "cache_read_per_mtok", 0) or 0
            )
            if inp == 0 and out == 0:
                entry["status"] = "$0"
            else:
                entry["status"] = "OK"
    except Exception:
        pass
    return entry
