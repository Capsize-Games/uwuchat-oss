"""Streaming execution helpers for generation.

Extracted from ``generation_execution_support``.  Owns the workflow
stream loop: callback wiring, CUDA preparation, generation-kwarg
normalization, and raw message collection.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from airunner_services.llm.managers.mixins.generation_execution_support._backend import (
    _active_chat_models,
    _has_tool_choice,
    _is_openai_backend,
    _model_supports_reasoning,
)
from airunner_services.llm.managers.mixins.generation_stream_support import (
    create_streaming_callback,
    create_thinking_callback,
    handle_generation_error,
    handle_interrupted_generation,
)
from airunner_services.llm.managers.mixins.generation_workflow_support import (
    clamp_generation_tokens,
    sync_request_scope_to_workflow_manager,
)
from airunner_services.llm.managers.request_preparation import (
    extract_request_images,
)


def run_generation_stream(
    owner,
    prompt: str,
    llm_request: Optional[Any],
    complete_response,
    sequence_counter,
) -> Dict[str, Any]:
    """Run the generation stream and return the captured workflow result."""
    sync_request_scope_to_workflow_manager(owner)
    # Bind the workflow manager to a local so a concurrent unload cannot null
    # it out from under us mid-stream. The image-generation flow unloads the
    # LLM (LLM_UNLOAD_SIGNAL) to free VRAM for the art model; if that fires
    # while a generation is finalizing, ``owner._workflow_manager`` becomes
    # None and the ``finally`` below crashed with
    # ``'NoneType' object has no attribute 'set_token_callback'``.
    workflow_manager = owner._workflow_manager
    if workflow_manager is None:
        owner.logger.warning(
            "Generation requested with no workflow manager loaded "
            "(model unloaded?); skipping stream."
        )
        return {"messages": []}

    def _do_reset() -> None:
        complete_response[0] = ""
        sequence_counter[0] = 0

    workflow_manager._reset_stream_state = _do_reset
    callback = create_streaming_callback(
        owner, llm_request, complete_response, sequence_counter
    )
    workflow_manager.set_token_callback(callback)
    thinking_callback = create_thinking_callback(
        owner, llm_request, sequence_counter
    )
    if hasattr(workflow_manager, "set_thinking_callback"):
        workflow_manager.set_thinking_callback(thinking_callback)
    if hasattr(workflow_manager, "set_interrupted"):
        workflow_manager.set_interrupted(False)
    try:
        return _stream_generation(
            owner, prompt, llm_request, complete_response, sequence_counter
        )
    finally:
        workflow_manager.set_token_callback(None)
        if hasattr(workflow_manager, "set_thinking_callback"):
            workflow_manager.set_thinking_callback(None)
        workflow_manager._reset_stream_state = None
        owner._interrupted = False
        if hasattr(workflow_manager, "set_interrupted"):
            workflow_manager.set_interrupted(False)


def _stream_generation(
    owner,
    prompt: str,
    llm_request: Optional[Any],
    complete_response,
    sequence_counter,
) -> Dict[str, Any]:
    """Execute the workflow stream and convert it into the result dict."""
    try:
        _prepare_cuda()
        generation_kwargs = (
            llm_request.to_generation_kwargs() if llm_request else {}
        )
        _normalize_generation_kwargs(owner, llm_request, generation_kwargs)
        images = extract_request_images(llm_request)
        if images:
            owner.logger.info(
                "Passing %s image(s) to workflow stream", len(images)
            )
        result = _stream_messages(owner, prompt, generation_kwargs, images)
        if owner._interrupted:
            interrupt_msg = handle_interrupted_generation(
                owner, llm_request, sequence_counter[0]
            )
            complete_response[0] += interrupt_msg
            return {"messages": []}
        return result
    except Exception as exc:
        owner._turn_failed = True
        complete_response[0] = handle_generation_error(
            owner, exc, llm_request
        )
        return {"messages": []}


def _prepare_cuda() -> None:
    """Clear CUDA caches before streaming when CUDA is available."""
    try:
        import torch
        if not torch.cuda.is_available():
            return
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
    except ImportError:
        pass


# Parameters only understood by HuggingFace / local backends.
# OpenAI-compatible APIs reject these with a TypeError.
_HF_ONLY_KWARGS = frozenset(
    {
        "do_sample",
        "early_stopping",
        "eta_cutoff",
        "length_penalty",
        "min_length",
        "no_repeat_ngram_size",
        "num_beams",
        "num_return_sequences",
        "repetition_penalty",
        "top_k",
        "use_cache",
    }
)


def _normalize_generation_kwargs(
    owner, llm_request, generation_kwargs: dict
) -> None:
    """Normalize generation kwargs before streaming."""
    if "max_tokens" in generation_kwargs:
        generation_kwargs["max_new_tokens"] = generation_kwargs.pop(
            "max_tokens"
        )
    clamp_generation_tokens(owner, generation_kwargs)
    if _is_openai_backend(owner):
        for key in _HF_ONLY_KWARGS:
            generation_kwargs.pop(key, None)
        if "max_new_tokens" in generation_kwargs:
            generation_kwargs["max_tokens"] = generation_kwargs.pop(
                "max_new_tokens"
            )
        # enable_thinking is a provider-specific param (e.g. DeepSeek).
        # The OpenAI client rejects unknown top-level kwargs, so move it
        # into extra_body which is passed through without validation.
        # NOTE: thinking + tools(auto) is fine for DeepSeek, but thinking +
        # a *restrictive* tool_choice (any/required/named function) is
        # rejected ("Thinking mode does not support this tool_choice").
        # That restrictive choice can be bound mid-graph (forced-tool
        # policy / RAG-search), so the authoritative strip happens at the
        # stream call site (see node_streaming_response_helper). Here we
        # only avoid building reasoning when a restrictive choice is
        # already active up front.
        has_tc = _has_tool_choice(owner)
        enable_thinking = generation_kwargs.pop("enable_thinking", None)
        # reasoning_effort must also be popped — OpenRouter interprets a
        # top-level reasoning_effort kwarg as enabling thinking mode, which
        # causes the same 400 as extra_body.reasoning when tool_choice is
        # restrictive.  The value is read from llm_request directly when
        # building extra_body below.
        generation_kwargs.pop("reasoning_effort", None)
        owner.logger.info(
            "[NORMALIZE] enable_thinking=%r has_tc=%r",
            enable_thinking,
            has_tc,
        )
        if enable_thinking and not has_tc:
            if _model_supports_reasoning(owner):
                effort = (
                    getattr(llm_request, "reasoning_effort", None)
                    or "medium"
                )
                extra_body = generation_kwargs.get("extra_body") or {}
                extra_body["reasoning"] = {
                    "effort": effort,
                    "exclude": False,
                }
                generation_kwargs["extra_body"] = extra_body
                owner.logger.info(
                    "[NORMALIZE] Added extra_body.reasoning effort=%s",
                    effort,
                )
            else:
                owner.logger.info(
                    "[NORMALIZE] Skipped extra_body.reasoning — "
                    "model does not support it"
                )
    owner.logger.debug(
        "llm_request.max_new_tokens=%s",
        llm_request.max_new_tokens if llm_request else "NO REQUEST",
    )
    owner.logger.debug(
        "generation_kwargs keys: %s", list(generation_kwargs.keys())
    )
    owner.logger.debug(
        "generation_kwargs.get('max_new_tokens')=%s",
        generation_kwargs.get("max_new_tokens", "NOT SET"),
    )


def _stream_messages(
    owner, prompt: str, generation_kwargs: dict, images
) -> Dict[str, Any]:
    """Collect raw and final workflow messages from the stream."""
    result_messages = []
    raw_messages = []
    for message in owner._workflow_manager.stream(
        prompt, generation_kwargs, images=images
    ):
        if owner._interrupted:
            owner.logger.info(
                "Stream interrupted - breaking out of generation"
            )
            break
        raw_messages.append(message)
        if not getattr(message, "tool_calls", None):
            result_messages.append(message)
    return {"messages": result_messages, "raw_messages": raw_messages}
