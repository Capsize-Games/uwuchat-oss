"""Runtime plumbing helpers for runtime-backed LLM routes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Iterator, List, Optional

from fastapi import HTTPException, Request, WebSocket

from airunner_services.ipc.messages import (
    EnvelopeStatus,
    RequestEnvelope,
    StreamDelta,
)
from airunner_services.runtimes.base import RuntimeClient
from airunner_services.runtimes.contracts import (
    ChatMessage as RuntimeChatMessage,
    LLMInvocationRequest,
    MessageRole,
    RuntimeAction,
    RuntimeKind,
)
from airunner_services.runtimes.registry import RuntimeRegistry

from airunner_services.contract_enums import ModelService

from .llm_contracts import ChatMessage
from .llm_runtime_rag import (
    _build_envelope_metadata,
    _parse_raw_messages,
    _persist_rag_to_conversation,
    _resolve_rag_metadata,
)

# Maximum output tokens per subscription tier (prevents runaway
# generation costs).  Re-exported from here so both llm_stream_routes
# (where it is enforced at the boundary) and callers in this module
# can reference the same ceiling without a circular import.
MAX_OUTPUT_TOKENS: dict[str, int] = {
    "trial": 300,
    "lite": 400,
    "companion": 500,
    "connection": 600,
    "devoted": 800,
}
DEFAULT_MAX_OUTPUT_TOKENS = 500
# Code-mode conversations get the framework chat-action budget (8192)
# instead of the companion-tier ceiling: code-mode replies narrate tool
# results and can legitimately run long (the inline agent tools do real
# work).  The tier ceiling exists for companion chat, where a 500-token
# reply is already generous.
CODE_MODE_MAX_OUTPUT_TOKENS = 8192


def _conversation_is_code_mode(conversation_id: int | None) -> bool:
    """Return True when *conversation_id* has UwUchat code mode on.

    Guarded project import: ``projects.<active>.server.code_mode_service``
    is UwUchat-specific, so any import error (or a non-UwUchat
    deployment) returns False — a pure no-op.
    """
    if not conversation_id:
        return False
    try:
        import importlib
        import os

        project = os.environ.get("AIRUNNER_PROJECT", "")
        if not project:
            from airunner_services.conf import settings

            project = getattr(settings, "AIRUNNER_PROJECT", "") or ""
        if not project:
            return False
        mod = importlib.import_module(
            f"projects.{project}.server.code_mode_service"
        )
        func = getattr(mod, "get_code_mode", None)
        if func is None:
            return False
        return bool(func(conversation_id))
    except Exception:
        return False


@dataclass
class LLMRuntimeResult:
    """One non-streaming LLM runtime response plus token usage.

    Token counts come from the runtime envelope metadata and default
    to 0 when the runtime did not report them.
    """

    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


def get_runtime_registry(request: Request) -> Optional[RuntimeRegistry]:
    """Return the runtime registry attached to the FastAPI app."""
    return getattr(request.app.state, "runtime_registry", None)


def require_runtime_registry(request: Request) -> RuntimeRegistry:
    """Return the runtime registry or raise when it is unavailable."""
    runtime_registry = get_runtime_registry(request)
    if runtime_registry is None:
        raise HTTPException(status_code=503, detail="LLM runtime unavailable")
    return runtime_registry


def require_websocket_runtime_registry(
    websocket: WebSocket,
) -> RuntimeRegistry:
    """Return the runtime registry for a websocket session."""
    app = getattr(websocket, "app", None)
    state = getattr(app, "state", None)
    runtime_registry = getattr(state, "runtime_registry", None)
    if runtime_registry is None:
        raise HTTPException(status_code=503, detail="LLM runtime unavailable")
    return runtime_registry


def resolve_llm_client(registry: RuntimeRegistry) -> RuntimeClient:
    """Resolve the single local LLM runtime client."""
    try:
        return registry.resolve(RuntimeKind.LLM, provider=ModelService.LOCAL.value)
    except KeyError as exc:
        raise HTTPException(
            status_code=503,
            detail="LLM runtime unavailable",
        ) from exc


def to_runtime_messages(
    messages: List[ChatMessage],
) -> List[RuntimeChatMessage]:
    """Convert API messages into the neutral runtime contract format."""
    runtime_messages = []
    for message in messages:
        try:
            role = MessageRole(message.role)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported chat role: {message.role}",
            ) from exc
        runtime_messages.append(
            RuntimeChatMessage(role=role, content=message.content),
        )
    return runtime_messages


def runtime_error_status(response: Any) -> int:
    """Return the best HTTP status code for a runtime failure envelope."""
    error = getattr(response, "error", None)
    if error is not None and getattr(error, "code", "").endswith("_timeout"):
        return 504
    return 502


def raise_for_runtime_error(response: Any) -> None:
    """Raise an HTTP exception for a failed runtime response."""
    if response.status is EnvelopeStatus.SUCCEEDED:
        return
    detail = "LLM runtime request failed"
    if response.error is not None:
        detail = response.error.message
    raise HTTPException(
        status_code=runtime_error_status(response),
        detail=detail,
    )


async def invoke_llm_runtime(
    client: RuntimeClient,
    messages: List[RuntimeChatMessage],
    model: Optional[str],
    gguf_runtime_profile: Optional[str],
    temperature: float,
    max_tokens: Optional[int],
    stateless: bool = False,
) -> LLMRuntimeResult:
    """Invoke the configured LLM runtime client.

    When ``stateless`` is True the request bypasses the chat agent: no
    conversation, chatbot, or message rows are created or persisted. Use it
    for one-shot utility completions (e.g. character generation).

    Returns an :class:`LLMRuntimeResult` carrying the generated content
    plus the token usage reported by the runtime envelope metadata.
    """
    metadata: dict = {}
    if gguf_runtime_profile:
        metadata["gguf_runtime_profile"] = gguf_runtime_profile
    if stateless:
        metadata["stateless"] = True
    invocation = LLMInvocationRequest(
        messages=messages,
        model=model,
        metadata=metadata,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    envelope = RequestEnvelope(
        runtime=RuntimeKind.LLM,
        action=RuntimeAction.INVOKE,
        provider=ModelService.LOCAL.value,
        payload=invocation.model_dump(),
    )
    response = await asyncio.to_thread(client.invoke, envelope)
    raise_for_runtime_error(response)
    resp_meta = getattr(response, "metadata", None) or {}
    return LLMRuntimeResult(
        content=str(response.payload.get("content", "")),
        prompt_tokens=int(resp_meta.get("prompt_tokens", 0) or 0),
        completion_tokens=int(resp_meta.get("completion_tokens", 0) or 0),
        total_tokens=int(resp_meta.get("total_tokens", 0) or 0),
    )


async def run_runtime_action(
    client: RuntimeClient,
    action: RuntimeAction,
) -> None:
    """Invoke a control action on the active LLM runtime."""
    response = await asyncio.to_thread(
        client.invoke,
        RequestEnvelope(
            runtime=RuntimeKind.LLM,
            action=action,
            provider=ModelService.LOCAL.value,
        ),
    )
    raise_for_runtime_error(response)


_SENTINEL = object()


def _next_item(iterator: Iterator) -> Any:
    """Return the next item from *iterator* or _SENTINEL when exhausted."""
    return next(iterator, _SENTINEL)


async def next_stream_delta(iterator: Iterator) -> StreamDelta:
    """Read one runtime stream delta without blocking the event loop."""
    result = await asyncio.to_thread(_next_item, iterator)
    if result is _SENTINEL:
        raise StopAsyncIteration
    return result


async def stream_runtime(client: RuntimeClient, envelope: RequestEnvelope):
    """Yield runtime stream deltas from a blocking client iterator."""
    iterator = iter(client.stream(envelope))
    while True:
        try:
            yield await next_stream_delta(iterator)
        except StopAsyncIteration:
            return


_ROLE_MAP: dict[str, MessageRole] = {
    "user": MessageRole.USER,
    "assistant": MessageRole.ASSISTANT,
    "system": MessageRole.SYSTEM,
}


def _parse_messages(
    raw_messages: list[dict[str, Any]],
) -> list[RuntimeChatMessage]:
    """Convert API-format messages to runtime chat messages."""
    result: list[RuntimeChatMessage] = []
    for msg in raw_messages:
        role_str = str(msg.get("role", "user")).lower()
        role = _ROLE_MAP.get(role_str, MessageRole.USER)
        content = str(msg.get("content", "")).strip()
        if content:
            result.append(RuntimeChatMessage(role=role, content=content))
    return result


def websocket_envelope(
    data: dict[str, Any],
    max_tokens_ceiling: int | None = None,
) -> RequestEnvelope:
    """Build one streaming runtime envelope from a websocket payload.

    When *max_tokens_ceiling* is set, the client-supplied (or absent)
    ``max_tokens`` is clamped before it reaches the LLM invocation.
    """
    raw_messages = _parse_raw_messages(data)
    active_ids: list[int] = data.get("active_document_ids") or []
    rag_meta = _resolve_rag_metadata(active_ids)

    messages = _parse_messages(raw_messages)
    metadata = _build_envelope_metadata(data)
    if active_ids:
        metadata["active_document_ids"] = active_ids

    conversation_id = data.get("conversation_id")
    model_path = data.get("model")
    if conversation_id:
        _persist_rag_to_conversation(
            conversation_id,
            _resolve_model_for_storage(model_path),
            rag_meta,
            rag_system_message=None,
        )

    raw_max_tokens = data.get("max_tokens")
    if max_tokens_ceiling is not None:
        if raw_max_tokens is None:
            max_tokens = max_tokens_ceiling
        else:
            max_tokens = min(int(raw_max_tokens), max_tokens_ceiling)
    else:
        max_tokens = raw_max_tokens

    payload = LLMInvocationRequest(
        model=data.get("model"),
        messages=messages,
        max_tokens=max_tokens,
        metadata=metadata,
        temperature=float(data.get("temperature", 0.7)),
        stream=True,
    )
    return RequestEnvelope(
        runtime=RuntimeKind.LLM,
        action=RuntimeAction.INVOKE,
        provider=ModelService.LOCAL.value,
        stream=True,
        payload=payload.model_dump(),
    )


def _resolve_model_for_storage(model: str | None) -> str | None:
    """Resolve *model* through the project router for storage.

    Returns the routed model name when a project routing rule exists
    for ``DIALOGUE``, otherwise returns *model* unchanged.
    """
    if not model:
        return model
    try:
        from airunner_services.llm.model_router import load_project_router

        router = load_project_router()
        if router is not None:
            rule = router.rule("DIALOGUE")
            if rule:
                return rule.get("model", model)
    except Exception:
        pass
    return model
