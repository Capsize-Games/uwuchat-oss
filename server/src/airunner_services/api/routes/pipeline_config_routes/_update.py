"""Upsert pipeline-config RPC route (create + update)."""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.api.routes.events_rpc import (
    _rpc_error_response,
    _rpc_register,
)
from airunner_services.api.routes.pipeline_config_routes._helpers import (
    _deep_merge,
)
from airunner_services.api.routes.pipeline_config_routes._superuser import (
    _require_superuser,
)

logger = logging.getLogger(__name__)


@_rpc_register("PUT", "/api/admin/pipeline-config/{key}")
async def _put_pipeline_config(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Upsert overrides for one pipeline key (deep-merge)."""
    ws = kw.get("ws")
    account_id = _require_superuser(ws)
    if account_id is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    key = (kw.get("path_params") or {}).get("key", "")
    if not key:
        return {"status": 400, "body": {"error": "key is required"}}

    payload = body or {}
    from airunner_services.llm.pipeline_loader import load_pipeline

    merged = load_pipeline()
    if key not in merged:
        return {
            "status": 404,
            "body": {"error": f"Unknown pipeline key: {key}"},
        }

    try:
        from airunner_services.database.models.pipeline_config import (
            PipelineConfig,
        )
        from airunner_services.llm.pipeline_loader import reload_pipeline

        row = (
            PipelineConfig.objects.query()
            .filter(PipelineConfig.pipeline_key == key)
            .first()
        )
        if row:
            existing = getattr(row, "overrides", {}) or {}
            new_overrides = _deep_merge(existing, payload)
            PipelineConfig.objects.update(
                row.id,
                overrides=new_overrides,
                updated_by=str(account_id),
            )
        else:
            new_overrides = dict(payload)
            PipelineConfig.objects.create(
                pipeline_key=key,
                overrides=new_overrides,
                updated_by=str(account_id),
            )
        reload_pipeline()
        return {
            "status": 200,
            "body": {
                "key": key,
                "merged_config": load_pipeline().get(key, {}),
            },
        }
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="error",
        )
