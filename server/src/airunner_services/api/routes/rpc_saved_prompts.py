"""RPC handlers: saved art prompts."""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.api.routes.events import (
    _rpc_error_response,
    _rpc_register,
)

logger = logging.getLogger(__name__)


def _prompt_dict(item) -> dict:
    """Build a prompt response dict from one row."""
    return {
        "id": item.id,
        "version": item.version or "",
        "prompt": item.prompt or "",
        "secondary_prompt": item.secondary_prompt or "",
        "negative_prompt": item.negative_prompt or "",
        "secondary_negative_prompt": (item.secondary_negative_prompt or ""),
    }


@_rpc_register("GET", "/api/v1/art/saved-prompts")
async def _rpc_saved_prompts_list(body: dict, **kw: Any) -> dict[str, Any]:
    try:
        from airunner_services.database.models.saved_prompt import (
            SavedPrompt,
        )

        version_filter = (body or {}).get("version") or None
        q = SavedPrompt.objects.query()
        if version_filter:
            q = q.filter(SavedPrompt.version == version_filter)
        items = q.all()
        return {
            "status": 200,
            "body": {"prompts": [_prompt_dict(item) for item in items]},
        }
    except Exception:
        return {"status": 200, "body": {"prompts": []}}


@_rpc_register("POST", "/api/v1/art/saved-prompts")
async def _rpc_saved_prompts_create(body: dict, **kw: Any) -> dict[str, Any]:
    try:
        from airunner_services.database.models.saved_prompt import (
            SavedPrompt,
        )

        with SavedPrompt.objects.transaction() as tx:
            item = SavedPrompt(
                version=body.get("version") or None,
                prompt=body.get("prompt", ""),
                secondary_prompt=body.get("secondary_prompt", ""),
                negative_prompt=body.get("negative_prompt", ""),
                secondary_negative_prompt=body.get(
                    "secondary_negative_prompt", ""
                ),
            )
            tx.add(item)
            tx.flush()
            return {"status": 201, "body": _prompt_dict(item)}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="saved prompt create failed",
        )


@_rpc_register("DELETE", "/api/v1/art/saved-prompts/{prompt_id}")
async def _rpc_saved_prompts_delete(body: dict, **kw: Any) -> dict[str, Any]:
    pp: dict = kw.get("path_params", {})
    raw_id = pp.get("prompt_id", "")
    if not raw_id.isdigit():
        return {"status": 400, "body": {"error": "Invalid ID"}}
    try:
        from airunner_services.database.models.saved_prompt import (
            SavedPrompt,
        )

        prompt_id = int(raw_id)
        with SavedPrompt.objects.transaction() as tx:
            item = (
                tx.query(SavedPrompt)
                .filter(SavedPrompt.id == prompt_id)
                .first()
            )
            if not item:
                return {"status": 404, "body": {"error": "Not found"}}
            tx.delete(item)
            return {"status": 200, "body": {"ok": True}}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="saved prompt delete failed",
        )
