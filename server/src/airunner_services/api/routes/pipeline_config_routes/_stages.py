"""Pipeline-stage RPC routes (list stages + save prompt override)."""

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
from airunner_services.api.routes.pipeline_config_routes._stages_meta import (
    _PIPELINE_STAGES,
    _STAGE_ORDER,
)
from airunner_services.api.routes.pipeline_config_routes._superuser import (
    _require_superuser,
)

logger = logging.getLogger(__name__)


@_rpc_register("GET", "/api/admin/pipeline-stages")
async def _list_pipeline_stages(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Return all 10 pipeline stages with metadata and prompts."""
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    from airunner_services.llm.pipeline_loader import load_pipeline

    merged = load_pipeline()
    result = []
    for key in _STAGE_ORDER:
        meta = next((s for s in _PIPELINE_STAGES if s["key"] == key), None)
        cfg = merged.get(key, {})
        entry = {
            "key": key,
            "label": meta["label"] if meta else key,
            "description": meta["description"] if meta else "",
            "trigger": meta["trigger"] if meta else "",
            "model": cfg.get("model"),
            "enabled": cfg.get("enabled", True),
            "config": {
                k: v
                for k, v in cfg.items()
                if k
                not in (
                    "model",
                    "enabled",
                    "provider",
                    "prompt_template",
                    "tiers",
                    "openrouter_provider",
                    "openrouter_provider_category",
                    "safety",
                    "streaming",
                )
            },
            "prompt_template": meta["prompt_template"]
            if meta
            else None,
            "prompt_source": meta["prompt_source"] if meta else None,
        }
        result.append(entry)
    return {"status": 200, "body": result}


@_rpc_register("POST", "/api/admin/pipeline-stages/{key}/prompt")
async def _save_stage_prompt(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Save a prompt template override for one pipeline stage."""
    ws = kw.get("ws")
    account_id = _require_superuser(ws)
    if account_id is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    key = (kw.get("path_params") or {}).get("key", "")
    if not key:
        return {"status": 400, "body": {"error": "key is required"}}

    payload = body or {}
    prompt = payload.get("prompt_template")
    if prompt is None or not isinstance(prompt, str):
        return {
            "status": 400,
            "body": {"error": "prompt_template string is required"},
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
        existing = {}
        if row:
            existing = getattr(row, "overrides", {}) or {}
        new_overrides = _deep_merge(existing, {"prompt_template": prompt})
        if row:
            PipelineConfig.objects.update(
                row.id,
                overrides=new_overrides,
                updated_by=str(account_id),
            )
        else:
            PipelineConfig.objects.create(
                pipeline_key=key,
                overrides=new_overrides,
                updated_by=str(account_id),
            )
        reload_pipeline()
        return {"status": 200, "body": {"key": key, "saved": True}}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="error",
        )
