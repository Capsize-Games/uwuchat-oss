"""Admin HTTP endpoints for call-chain detail.

Provides ordinary HTTP routes for fetching per-message cost breakdowns
so the inline cost table works on page reload (no WebSocket dependency).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from airunner_services.api.server_middleware import sanitized_http_exception

logger = logging.getLogger(__name__)

router = APIRouter()


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


@router.get("/call-chain/{call_chain_id}")
async def call_chain_detail(
    call_chain_id: str,
    req: Request,
    _account_id: int = Depends(_superuser_dep),
) -> dict:
    """Return the full call chain for one call_chain_id (HTTP)."""
    if not call_chain_id:
        raise HTTPException(
            status_code=400, detail="call_chain_id required"
        )
    return _build_call_chain(call_chain_id, requester_account_id=_account_id)


@router.get("/call-chain/by-turn/{turn_id}")
async def call_chain_by_turn(
    turn_id: int,
    req: Request,
    _account_id: int = Depends(_superuser_dep),
) -> dict:
    """Resolve a turn_id to its call_chain_id and return the chain."""
    try:
        from airunner_services.database.models.conversation_turn import (
            ConversationTurn,
        )

        turn = ConversationTurn.objects.get(turn_id)
        if turn is None:
            raise HTTPException(
                status_code=404, detail="Turn not found"
            )
        cid = getattr(turn, "call_chain_id", None)
        if not cid:
            raise HTTPException(
                status_code=404,
                detail="No call chain recorded for this turn",
            )
        return _build_call_chain(cid, requester_account_id=_account_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise sanitized_http_exception(
            exc,
            logger=logger,
            context="call chain by turn error",
        )


@router.get("/cost-by-turn")
async def cost_by_turn(
    req: Request,
    chatbot_id: int,
    _account_id: int = Depends(_superuser_dep),
) -> dict:
    """Return per-turn cost annotations, keyed by call_chain_id.

    Uses _sum_pipeline_usage() so the per-message badge numbers
    match the per-turn badge numbers (both sum the same rows).
    """
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
        raise sanitized_http_exception(
            exc,
            logger=logger,
            context="cost by turn error",
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
        "annotations": annotations,
        "total_cost_usd": round(total, 8),
    }


def _sum_pipeline_usage(call_chain_id: str) -> dict:
    """Return {cost_usd, input_tokens, output_tokens} for one chain.

    Both _build_call_chain() and cost_by_turn() route through this
    function so the two cost badges always sum the same set of rows.
    """
    from airunner_services.database.models.pipeline_token_usage import (
        PipelineTokenUsage,
    )

    rows = (
        PipelineTokenUsage.objects.query()
        .filter(PipelineTokenUsage.call_chain_id == call_chain_id)
        .all()
    )
    cost = 0.0
    inp = 0
    out = 0
    for row in rows:
        cost += float(getattr(row, "cost_usd", 0) or 0)
        inp += int(getattr(row, "input_tokens", 0) or 0)
        out += int(getattr(row, "output_tokens", 0) or 0)
    return {"cost_usd": cost, "input_tokens": inp, "output_tokens": out}


def _build_call_chain(
    call_chain_id: str,
    requester_account_id: int,
) -> dict:
    """Build a call-chain detail response from pipeline_token_usage."""
    try:
        from airunner_services.database.models.pipeline_token_usage import (
            PipelineTokenUsage,
        )

        rows = (
            PipelineTokenUsage.objects.query()
            .filter(PipelineTokenUsage.call_chain_id == call_chain_id)
            .order_by(PipelineTokenUsage.recorded_at.asc())
            .all()
        )
    except Exception as exc:
        raise sanitized_http_exception(
            exc,
            logger=logger,
            context="call chain build error",
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
                    if getattr(row, "complexity_score", None)
                    is not None
                    else None
                ),
                "prompt_char_count": getattr(
                    row, "prompt_char_count", None
                ),
                "response_char_count": getattr(
                    row, "response_char_count", None
                ),
                "tier_name": getattr(row, "tier_name", None),
                "recorded_at": (
                    getattr(row, "recorded_at", None).isoformat()
                    if getattr(row, "recorded_at", None)
                    else None
                ),
            }
        )

    # Attach prompt/response text when caller and row share same tenant.
    _attach_pipeline_text(
        steps, rows, requester_account_id=requester_account_id,
    )

    summary = _sum_pipeline_usage(call_chain_id)

    return {
        "call_chain_id": call_chain_id,
        "total_cost_usd": round(summary["cost_usd"], 8),
        "total_input_tokens": summary["input_tokens"],
        "total_output_tokens": summary["output_tokens"],
        "steps": steps,
        "trigger_type": "user_message",
    }


def _attach_pipeline_text(
    steps: list[dict],
    rows: list,
    *,
    requester_account_id: int,
) -> None:
    """Enrich *steps* with prompt/response text from PipelineCallContent.

    Security invariant: derives the requester's tenant identity from
    *requester_account_id* (the authenticated superuser's account),
    NOT from any ambient or client-supplied tenant context.  Only
    queries PipelineCallContent for rows whose ``tenant_key`` matches
    the requester's own tenant.  Cross-tenant lookups are never
    attempted — when the tenant_keys differ, the step is left without
    text fields (same as today).
    """
    from airunner_services.data.tenant import (
        set_tenant_key,
        tenant_key_from_schema,
    )

    requester_key = _resolve_tenant_key_for_account(
        requester_account_id,
    )
    if not requester_key:
        return

    # Collect (usage_id, idx) pairs for rows matching the requester.
    targets: list[tuple[int, int]] = []
    for i, row in enumerate(rows):
        row_tenant = getattr(row, "tenant_key", None)
        if not row_tenant:
            continue
        # Recover raw key from potentially-prefixed schema name.
        resolved = tenant_key_from_schema(row_tenant) or row_tenant
        if resolved != requester_key:
            continue
        usage_id = getattr(row, "id", None)
        if usage_id is not None:
            targets.append((int(usage_id), i))

    if not targets:
        return

    try:
        from airunner_services.database import session_scope
        from airunner_services.database.models.pipeline_call_content import (
            PipelineCallContent,
        )

        usage_ids = [t[0] for t in targets]
        set_tenant_key(requester_key)
        with session_scope():
            rows_pcc = (
                PipelineCallContent.objects.query()
                .filter(
                    PipelineCallContent.usage_id.in_(usage_ids)
                )
                .all()
            )
        text_by_usage: dict[int, dict[str, str | None]] = {}
        for pcc in rows_pcc:
            text_by_usage[int(getattr(pcc, "usage_id", 0))] = {
                "prompt_text": getattr(pcc, "prompt_text", None),
                "response_text": getattr(pcc, "response_text", None),
            }
        for usage_id, idx in targets:
            entry = text_by_usage.get(usage_id)
            if entry:
                steps[idx]["prompt_text"] = entry["prompt_text"]
                steps[idx]["response_text"] = entry["response_text"]
    except Exception:
        logger.debug(
            "Failed to attach pipeline text for call_chain",
            exc_info=True,
        )


def _resolve_tenant_key_for_account(account_id: int) -> str | None:
    """Return the raw tenant key for *account_id*, or None on failure.

    Looks up the Account row in the public schema and converts its
    ``tenant_schema`` column back to a raw key via
    :func:`tenant_key_from_schema`.  This is the authorized identity
    signal — never use ambient tenant context for read-path
    authorization.
    """
    try:
        from airunner_services.data.tenant import tenant_key_from_schema
        from extensions.auth.server.models import Account

        account = Account.objects.get(account_id)
        if account is None:
            return None
        schema = getattr(account, "tenant_schema", None)
        if not schema:
            return None
        return tenant_key_from_schema(schema)
    except Exception:
        return None
