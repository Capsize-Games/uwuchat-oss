"""Fire-and-forget token usage recording for the AI pipeline.

Call ``record_usage()`` after every pipeline LLM call.  Always write
in the ``public`` schema (not tenant-scoped).  Never raises, never
blocks the caller.

Only metadata (char counts, not content) is stored per
``CLAUDE.md`` Security and Privacy rules.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _resolve_pricing(
    model_id: str,
) -> dict[str, Optional[float]]:
    """Return {input, output, cache} snapshot pricing for *model_id*."""
    from airunner_services.llm.pricing import lookup_pricing

    p = lookup_pricing(model_id)
    return {
        "input": p.get("input"),
        "output": p.get("output"),
        "cache": p.get("cache"),
    }


def _calc_cost(
    inp: int,
    out: int,
    cache: int,
    p: dict[str, Optional[float]],
) -> Optional[float]:
    """Return cost_usd or None when pricing is unavailable."""
    ip = p.get("input")
    op = p.get("output")
    cp = p.get("cache")
    if ip is None and op is None and cp is None:
        return None
    from airunner_services.llm.pricing import compute_cost_usd

    return compute_cost_usd(inp, out, cache, ip or 0, op or 0, cp or 0)


def record_usage(
    pipeline_key: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    tenant_key: Optional[str] = None,
    account_id: Optional[int] = None,
    chatbot_id: Optional[int] = None,
    call_chain_id: Optional[str] = None,
    complexity_score: Optional[float] = None,
    tier_name: Optional[str] = None,
    risk_score: Optional[float] = None,
    risk_tier: Optional[str] = None,
    prompt_tokens_saved: Optional[int] = None,
    skipped: bool = False,
    prompt_char_count: Optional[int] = None,
    response_char_count: Optional[int] = None,
) -> Optional[int]:
    """Write one PipelineTokenUsage row and return its id.

    Returns the created row's ``id`` on success, or ``None`` when
    recording failed (never raises).
    """
    try:
        from airunner_services.database.models.pipeline_token_usage import (
            PipelineTokenUsage,
        )

        resolved = _resolve_account_id(account_id, tenant_key)
        p = _resolve_pricing(model_id)
        cost = _calc_cost(
            input_tokens, output_tokens, cache_read_tokens, p
        )
        row = PipelineTokenUsage.objects.create(
            pipeline_key=pipeline_key,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            tenant_key=tenant_key,
            account_id=resolved,
            chatbot_id=chatbot_id,
            call_chain_id=call_chain_id,
            complexity_score=complexity_score,
            tier_name=tier_name,
            risk_score=risk_score,
            risk_tier=risk_tier,
            prompt_tokens_saved=prompt_tokens_saved,
            skipped=skipped,
            prompt_char_count=prompt_char_count,
            response_char_count=response_char_count,
            input_price_per_mtok=p.get("input"),
            output_price_per_mtok=p.get("output"),
            cache_price_per_mtok=p.get("cache"),
            cost_usd=cost,
        )
        return int(getattr(row, "id", 0)) or None
    except Exception:
        logger.warning(
            "Failed to record token usage for %s", pipeline_key,
            exc_info=True,
        )
        return None


def _resolve_account_id(
    account_id: Optional[int],
    tenant_key: Optional[str],
) -> Optional[int]:
    """Return account_id, resolving from tenant_key if needed.

    Resolution order:
    1. Explicitly passed *account_id* (fast path, always preferred).
    2. ContextVar set by ``Worker.run_thread`` (per-item, no DB call).
    3. DB lookup from *tenant_key* (fallback for background code that
       has no access to the per-request ContextVar).
    """
    if account_id is not None:
        return account_id
    try:
        from airunner_services.data.tenant import get_account_id

        resolved = get_account_id()
        if resolved is not None:
            return resolved
    except Exception:
        pass
    if not tenant_key:
        return None
    try:
        from airunner_services.data.tenant import (
            account_id_from_tenant_key,
        )

        return account_id_from_tenant_key(tenant_key)
    except Exception:
        return None


def record_background_usage(
    pipeline_key: str,
    config: dict,
    response: Any,
    *,
    account_id: Optional[int] = None,
    chatbot_id: Optional[int] = None,
    tenant_key: Optional[str] = None,
    call_chain_id: Optional[str] = None,
    prompt_char_count: Optional[int] = None,
    response_char_count: Optional[int] = None,
) -> Optional[int]:
    """Record token usage for a background pipeline LLM call.

    Extracts token counts from the LangChain AIMessage response and
    delegates to :func:`record_usage`.  Never raises.

    Returns the created ``PipelineTokenUsage.id`` on success, or
    ``None`` when recording failed or was skipped (no tokens).

    Args:
        pipeline_key: e.g. ``"INTRA_SESSION_MOOD"``
        config: Merged pipeline config dict for this stage
        response: LangChain ``AIMessage`` from ``model.invoke()``
        account_id: Explicit account ID (request-scoped).  When None,
            resolved from *tenant_key* via the public ``accounts`` table.
    """
    try:
        model_id = config.get("model", "")
        usage_meta = getattr(response, "usage_metadata", None) or {}
        resp_meta = getattr(response, "response_metadata", None) or {}
        input_t = int(
            usage_meta.get("input_tokens", 0)
            or usage_meta.get("prompt_tokens", 0)
            or resp_meta.get("token_usage", {}).get("prompt_tokens", 0)
            or 0
        )
        output_t = int(
            usage_meta.get("output_tokens", 0)
            or usage_meta.get("completion_tokens", 0)
            or resp_meta.get("token_usage", {}).get("completion_tokens", 0)
            or 0
        )
        if input_t == 0 and output_t == 0:
            return None
        if not call_chain_id:
            import uuid
            call_chain_id = str(uuid.uuid4())
        return record_usage(
            pipeline_key=pipeline_key,
            model_id=model_id,
            input_tokens=input_t,
            output_tokens=output_t,
            account_id=_resolve_account_id(account_id, tenant_key),
            chatbot_id=chatbot_id,
            tenant_key=tenant_key,
            call_chain_id=call_chain_id,
            prompt_char_count=prompt_char_count,
            response_char_count=response_char_count,
        )
    except Exception:
        logger.debug(
            "Failed to record background usage for %s", pipeline_key,
            exc_info=True,
        )
        return None


def record_pipeline_call_text(
    usage_id: Optional[int],
    tenant_key: Optional[str],
    prompt_text: Optional[str],
    response_text: Optional[str],
) -> None:
    """Persist real prompt/response text for one pipeline call.

    Writes into the CALLING tenant's own schema (via *tenant_key*),
    linked to *usage_id* (the ``PipelineTokenUsage.id`` from the
    public schema).  Never raises.  No-ops when *usage_id* or
    *tenant_key* is missing — both are required to make a
    well-formed, linkable, tenant-scoped record.
    """
    if not usage_id or not tenant_key:
        return
    try:
        from airunner_services.data.tenant import set_tenant_key
        from airunner_services.database import session_scope
        from airunner_services.database.models.pipeline_call_content import (
            PipelineCallContent,
        )

        set_tenant_key(tenant_key)
        with session_scope():
            PipelineCallContent.objects.create(
                usage_id=usage_id,
                prompt_text=prompt_text,
                response_text=response_text,
            )
    except Exception:
        logger.debug(
            "Failed to record pipeline call text for usage_id=%s",
            usage_id,
            exc_info=True,
        )
