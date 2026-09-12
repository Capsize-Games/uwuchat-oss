"""Get-one pipeline-config RPC route."""

from __future__ import annotations

from typing import Any

from airunner_services.api.routes.events_rpc import _rpc_register
from airunner_services.api.routes.pipeline_config_routes._superuser import (
    _require_superuser,
)


@_rpc_register("GET", "/api/admin/pipeline-config/{key}")
async def _get_pipeline_config(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Get detailed config for one pipeline key."""
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    key = (kw.get("path_params") or {}).get("key", "")
    if not key:
        return {"status": 400, "body": {"error": "key is required"}}

    from airunner_services.llm.pipeline_loader import load_pipeline
    from airunner_services.llm.pipeline_defaults import PIPELINE_DEFAULTS

    merged = load_pipeline()
    if key not in merged:
        return {
            "status": 404,
            "body": {"error": f"Unknown pipeline key: {key}"},
        }

    db_overrides = {}
    try:
        from airunner_services.database.models.pipeline_config import (
            PipelineConfig,
        )

        row = (
            PipelineConfig.objects.query()
            .filter(PipelineConfig.pipeline_key == key)
            .first()
        )
        if row:
            db_overrides = getattr(row, "overrides", {}) or {}
    except Exception:
        pass

    return {
        "status": 200,
        "body": {
            "key": key,
            "merged_config": merged[key],
            "db_overrides": db_overrides,
            "defaults": PIPELINE_DEFAULTS.get(key, {}),
        },
    }
