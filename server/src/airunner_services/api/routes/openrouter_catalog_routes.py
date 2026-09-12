"""Admin RPC routes for OpenRouter model catalog."""

from __future__ import annotations

from typing import Any

from airunner_services.api.routes.events_rpc import (
    _rpc_error_response,
    _rpc_register,
)
import logging

logger = logging.getLogger(__name__)



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


def _model_to_dict(row) -> dict:
    """Serialize one OpenRouterModel row to a JSON-safe dict."""
    return {
        "model_id": getattr(row, "model_id", ""),
        "display_name": getattr(row, "display_name", ""),
        "input_price_per_mtok": (
            float(getattr(row, "input_price_per_mtok", 0) or 0)
        ),
        "output_price_per_mtok": (
            float(getattr(row, "output_price_per_mtok", 0) or 0)
        ),
        "cache_read_per_mtok": (
            float(getattr(row, "cache_read_per_mtok", 0) or 0)
        ),
        "context_length": getattr(row, "context_length", None),
        "latency_p50_ms": getattr(row, "latency_p50_ms", None),
        "throughput_tps": (
            float(getattr(row, "throughput_tps", 0) or 0)
            if getattr(row, "throughput_tps", None) is not None
            else None
        ),
        "fetched_at": (
            getattr(row, "fetched_at", None).isoformat()
            if getattr(row, "fetched_at", None)
            else None
        ),
    }


@_rpc_register("GET", "/api/admin/openrouter-models")
async def _list_openrouter_models(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """List all cached OpenRouter models, cheapest first."""
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    try:
        from airunner_services.llm.openrouter_catalog import list_models

        rows = list_models()
        return {
            "status": 200,
            "body": [_model_to_dict(r) for r in rows],
        }
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="error",
        )


@_rpc_register("GET", "/api/admin/openrouter-models/{model_id}")
async def _get_openrouter_model(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Get one cached OpenRouter model by ID."""
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    model_id_encoded = (kw.get("path_params") or {}).get(
        "model_id", ""
    )
    if not model_id_encoded:
        return {
            "status": 400,
            "body": {"error": "model_id is required"},
        }

    from urllib.parse import unquote

    model_id = unquote(model_id_encoded)

    try:
        from airunner_services.llm.openrouter_catalog import get_model

        row = get_model(model_id)
        if row is None:
            return {
                "status": 404,
                "body": {"error": f"Model not found: {model_id}"},
            }
        result = _model_to_dict(row)
        result["providers_json"] = getattr(
            row, "providers_json", []
        )
        return {"status": 200, "body": result}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="error",
        )


@_rpc_register("POST", "/api/admin/openrouter-models/sync")
async def _sync_openrouter_models(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Trigger an OpenRouter catalog sync (superuser only)."""
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    from airunner_services.api.routes.token_usage_routes import (
        _fetch_failed,
        _fetch_in_flight,
    )

    _fetch_failed.clear()
    _fetch_in_flight.clear()

    from airunner_services.llm.openrouter_catalog import sync_catalog

    count = sync_catalog()
    return {"status": 200, "body": {"synced": count}}
