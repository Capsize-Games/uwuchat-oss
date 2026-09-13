"""Delete pipeline-config RPC route."""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.api.routes.events_rpc import (
    _rpc_error_response,
    _rpc_register,
)
from airunner_services.api.routes.pipeline_config_routes._superuser import (
    _require_superuser,
)

logger = logging.getLogger(__name__)


@_rpc_register("DELETE", "/api/admin/pipeline-config/{key}")
async def _delete_pipeline_config(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Reset overrides for one key (set to empty dict)."""
    ws = kw.get("ws")
    account_id = _require_superuser(ws)
    if account_id is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    key = (kw.get("path_params") or {}).get("key", "")
    if not key:
        return {"status": 400, "body": {"error": "key is required"}}

    try:
        from airunner_services.database.models.pipeline_config import (
            PipelineConfig,
        )
        from airunner_services.llm.pipeline_loader import (
            reload_pipeline,
        )

        row = (
            PipelineConfig.objects.query()
            .filter(PipelineConfig.pipeline_key == key)
            .first()
        )
        if row:
            PipelineConfig.objects.update(
                row.id,
                overrides={},
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
