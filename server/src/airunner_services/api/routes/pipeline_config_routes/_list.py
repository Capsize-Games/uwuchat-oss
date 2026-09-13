"""List pipeline-config RPC route."""

from __future__ import annotations

from typing import Any

from airunner_services.api.routes.events_rpc import _rpc_register
from airunner_services.api.routes.pipeline_config_routes._superuser import (
    _require_superuser,
)


@_rpc_register("GET", "/api/admin/pipeline-config")
async def _list_pipeline_config(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """List all pipeline keys with merged config."""
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    from airunner_services.llm.pipeline_loader import load_pipeline

    merged = load_pipeline()
    try:
        from airunner_services.database.models.pipeline_config import (
            PipelineConfig,
        )

        db_rows = {
            r.pipeline_key: r
            for r in PipelineConfig.objects.query().all()
        }
    except Exception:
        db_rows = {}

    result = []
    for key in sorted(merged.keys()):
        has_db = key in db_rows and bool(
            getattr(db_rows[key], "overrides", None)
        )
        result.append(
            {
                "key": key,
                "merged_config": merged[key],
                "has_db_override": has_db,
            }
        )
    return {"status": 200, "body": result}
