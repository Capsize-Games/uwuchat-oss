"""RPC handlers for character generation and settings presets."""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.api.routes.character_utils import (
    build_character_prompt,
    build_uwu_identity_prompt,
    parse_llm_json,
)
from airunner_services.api.routes.events import (
    _rpc_error_response,
    _rpc_register,
)
from airunner_services.api.ws_tenant import resolve_ws_tenant

logger = logging.getLogger(__name__)


def _char_auth(kw: dict) -> int | None:
    """Resolve and return the account_id from the WS context.

    Returns None when the socket is unauthenticated — callers must
    reject the request with a 401-equivalent response.
    """
    ws = kw.get("ws")
    if ws is None:
        return None
    _tenant, account_id = resolve_ws_tenant(ws)
    return account_id


def _get_registry(kw: dict) -> Any:
    ws = kw.get("ws")
    app_state = getattr(getattr(ws, "app", None), "state", None)
    return getattr(app_state, "runtime_registry", None) if app_state else None


def _record_character_usage(result: Any) -> None:
    """Fire-and-forget PipelineTokenUsage for character creation.

    record_usage never raises, so a recording failure can't break the
    create flow.
    """
    from airunner_services.llm.active_call_chain import (
        get_active_call_chain,
    )
    from airunner_services.llm.pipeline_loader import pipeline_config
    from airunner_services.llm.token_usage import record_usage

    cfg = pipeline_config("CHARACTER_CREATION")
    record_usage(
        pipeline_key="CHARACTER_CREATION",
        model_id=cfg.get("model", ""),
        input_tokens=result.prompt_tokens,
        output_tokens=result.completion_tokens,
        call_chain_id=get_active_call_chain(),
    )


async def _invoke_character_llm(
    registry: Any, prompt_builder: Any, *prompt_args: Any
) -> str:
    """Run one stateless character-creation LLM call and record usage.

    Returns the raw LLM text; token usage is recorded fire-and-forget.
    """
    from airunner_services.api.routes.llm_runtime import (
        invoke_llm_runtime,
        resolve_llm_client,
    )
    from airunner_services.runtimes.contracts import (
        ChatMessage as RuntimeChatMessage,
        MessageRole,
    )

    client = resolve_llm_client(registry)
    system_content, user_content = prompt_builder(*prompt_args)
    messages = [
        RuntimeChatMessage(
            role=MessageRole.SYSTEM, content=system_content
        ),
        RuntimeChatMessage(role=MessageRole.USER, content=user_content),
    ]
    result = await invoke_llm_runtime(
        client, messages, None, None, 0.9, 500, stateless=True
    )
    _record_character_usage(result)
    return result.content


@_rpc_register("POST", "/api/v1/llm/generate-character")
async def _rpc_generate_character(body: dict, **kw: Any) -> dict[str, Any]:
    """Generate a character name/personality/backstory/greeting."""
    account_id = _char_auth(kw)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    registry = _get_registry(kw)
    if registry is None:
        return {"status": 503, "body": {"error": "LLM runtime unavailable"}}
    try:
        content = await _invoke_character_llm(
            registry,
            build_character_prompt,
            body.get("species", "Human"),
            body.get("gender", "Female"),
            body.get("vibe", "Cozy"),
            body.get("quirk", "Loves snacks"),
            body.get("affinity", "Stars"),
            body.get("age_era", "A Few Decades"),
        )
        return {"status": 200, "body": parse_llm_json(content)}
    except (ValueError, Exception) as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="generate-character error",
        )


@_rpc_register("POST", "/api/v1/llm/generate-uwu-identity")
async def _rpc_generate_uwu_identity(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Generate name/personality/backstory for a random UwU companion."""
    account_id = _char_auth(kw)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    registry = _get_registry(kw)
    if registry is None:
        return {"status": 503, "body": {"error": "LLM runtime unavailable"}}
    try:
        content = await _invoke_character_llm(
            registry,
            build_uwu_identity_prompt,
            body.get("gender", "Female"),
            body.get("personality_type", ""),
            body.get("species_data"),
            body.get("location"),
            body.get("age"),
        )
        return {"status": 200, "body": parse_llm_json(content)}
    except (ValueError, Exception) as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="generate-uwu-identity error",
        )


@_rpc_register("GET", "/api/v1/llm/settings-presets")
async def _rpc_llm_presets(body: dict, **kw: Any) -> dict[str, Any]:
    """List LLM settings presets."""
    account_id = _char_auth(kw)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    try:
        from airunner_services.api.routes.llm_settings_presets import (
            load_presets,
        )
        presets = load_presets()
        return {"status": 200, "body": {"presets": presets}}
    except Exception:
        return {"status": 200, "body": {"presets": []}}


@_rpc_register("POST", "/api/v1/llm/randomize-character")
async def _rpc_randomize_character(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Generate a complete randomized character profile."""
    account_id = _char_auth(kw)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    try:
        from airunner_services.api.routes.character_randomizer import (
            randomize_character,
        )
        allowed = body.get("allowed_species", None)
        profile = randomize_character(allowed_species=allowed)
        return {"status": 200, "body": profile}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="randomize-character error",
        )
