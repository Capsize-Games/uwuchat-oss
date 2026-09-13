"""Call-chain and cost-by-turn admin routes."""

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


@_rpc_register("GET", "/api/admin/call-chain/{call_chain_id}")
async def _call_chain_detail(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Return the full call chain for one call_chain_id."""
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    cid = (kw.get("path_params") or {}).get("call_chain_id", "")
    if not cid:
        return {"status": 400, "body": {"error": "call_chain_id required"}}

    try:
        from airunner_services.database.models.pipeline_token_usage import (
            PipelineTokenUsage,
        )

        rows = (
            PipelineTokenUsage.objects.query()
            .filter(PipelineTokenUsage.call_chain_id == cid)
            .order_by(PipelineTokenUsage.recorded_at.asc())
            .all()
        )
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="error",
        )

    steps = []
    for i, row in enumerate(rows):
        model = getattr(row, "model_id", "?")
        inp = int(getattr(row, "input_tokens", 0) or 0)
        out = int(getattr(row, "output_tokens", 0) or 0)
        cost = float(getattr(row, "cost_usd", 0) or 0)
        steps.append(
            {
                "sequence": i + 1,
                "pipeline_key": getattr(row, "pipeline_key", ""),
                "model_id": model,
                "input_tokens": inp,
                "output_tokens": out,
                "cache_read_tokens": int(
                    getattr(row, "cache_read_tokens", 0) or 0
                ),
                "cost_usd": round(cost, 8),
                "skipped": bool(getattr(row, "skipped", False)),
                "complexity_score": (
                    float(getattr(row, "complexity_score", 0))
                    if getattr(row, "complexity_score", None) is not None
                    else None
                ),
                "tier_name": getattr(row, "tier_name", None),
                "recorded_at": (
                    getattr(row, "recorded_at", None).isoformat()
                    if getattr(row, "recorded_at", None)
                    else None
                ),
            }
        )

    from airunner_services.api.routes.call_chain_routes import (
        _sum_pipeline_usage,
    )

    summary = _sum_pipeline_usage(cid)

    return {
        "status": 200,
        "body": {
            "call_chain_id": cid,
            "total_cost_usd": round(summary["cost_usd"], 8),
            "total_input_tokens": summary["input_tokens"],
            "total_output_tokens": summary["output_tokens"],
            "steps": steps,
            "trigger_type": "user_message",
        },
    }


@_rpc_register("GET", "/api/admin/call-chain/by-turn/{turn_id}")
async def _call_chain_by_turn(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Resolve a turn_id to its call_chain_id and return the chain."""
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    tid_raw = (kw.get("path_params") or {}).get("turn_id", "")
    try:
        turn_id = int(tid_raw)
    except (TypeError, ValueError):
        return {"status": 400, "body": {"error": "turn_id must be int"}}

    try:
        from airunner_services.database.models.conversation_turn import (
            ConversationTurn,
        )

        turn = ConversationTurn.objects.get(turn_id)
        if turn is None:
            return {
                "status": 404,
                "body": {"error": "Turn not found"},
            }
        cid = getattr(turn, "call_chain_id", None)
        if not cid:
            return {
                "status": 404,
                "body": {
                    "error": "No call chain recorded for this turn"
                },
            }
        # Forward to call-chain/{cid} logic
        return await _call_chain_detail(body, **{
            **kw,
            "path_params": {"call_chain_id": cid},
        })
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="error",
        )


@_rpc_register("GET", "/api/admin/cost-by-turn")
async def _cost_by_turn(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Return per-turn cost annotations for a chatbot, keyed by
    call_chain_id.  Routes through _sum_pipeline_usage() so the
    numbers match _build_call_chain()'s per-call-chain totals."""
    ws = kw.get("ws")
    if _require_superuser(ws) is None:
        return {"status": 403, "body": {"error": "Superuser required"}}

    cid_raw = body.get("chatbot_id")
    if not cid_raw:
        return {"status": 400, "body": {"error": "chatbot_id is required"}}
    try:
        chatbot_id = int(cid_raw)
    except (TypeError, ValueError):
        return {"status": 400, "body": {"error": "chatbot_id must be int"}}

    try:
        from airunner_services.database.models.pipeline_token_usage import (
            PipelineTokenUsage,
        )

        cids = (
            PipelineTokenUsage.objects.query(
                PipelineTokenUsage.call_chain_id
            )
            .filter(
                PipelineTokenUsage.chatbot_id == chatbot_id,
                PipelineTokenUsage.call_chain_id.isnot(None),
            )
            .distinct()
            .all()
        )
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="error",
        )

    from airunner_services.api.routes.call_chain_routes import (
        _sum_pipeline_usage,
    )

    annotations: dict = {}
    total = 0.0
    for (cid,) in cids:
        summary = _sum_pipeline_usage(cid)
        annotations[cid] = {
            "call_chain_id": cid,
            "cost_usd": round(summary["cost_usd"], 8),
            "input_tokens": summary["input_tokens"],
            "output_tokens": summary["output_tokens"],
        }
        total += summary["cost_usd"]

    return {
        "status": 200,
        "body": {
            "annotations": annotations,
            "total_cost_usd": round(total, 8),
        },
    }
