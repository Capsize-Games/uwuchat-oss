"""Chunk iteration and per-chunk processing for streamed responses.

``NodeStreamingLoopMixin`` drives the ``chat_model.stream`` generator
through the distributed limiter, applies PII masking before LLM
egress, and routes each chunk through thinking-block or visible-text
handling.
"""

from __future__ import annotations

from typing import Optional

from airunner_services.llm.managers.mixins.node_streaming_response_helpers import (
    accumulate_chunk,
    filter_tool_markup,
    store_visible_text,
)
from airunner_services.llm.managers.mixins.node_streaming_reasoning_guard import (
    strip_reasoning_for_forced_tool,
)
from airunner_services.llm.managers.mixins.node_streaming_state import (
    StreamingState,
)
from airunner_services.llm.managers.mixins.node_streaming_timing import (
    StreamTiming,
)
from airunner_services.llm.utils.stream_debug import print_stream_debug


# Internal framework diagnostic strings that must never reach the user
# as streamed text.  Some local models (GGUF/ollama) echo framework
# fallback text back into their tool-call message content; streaming it
# produces a raw diagnostic prefix before the real reply.
_INTERNAL_DIAGNOSTIC_MARKERS = (
    "The model attempted a tool-based response but did not produce a "
    "final reply. No changes were applied.",
    "The model produced an empty reply for this request. No changes "
    "were applied.",
    "The model used non-mutating tools",
    "The model inspected the workspace with read-only tools",
)


def _strip_internal_diagnostics(text: str) -> str:
    """Remove internal framework diagnostic strings from *text*."""
    if not text:
        return text
    stripped = text
    for marker in _INTERNAL_DIAGNOSTIC_MARKERS:
        if marker in stripped:
            stripped = stripped.replace(marker, "")
    return stripped


class NodeStreamingLoopMixin:
    """Iterate over and process one streamed response's chunks."""

    def _run_stream_loop(
        self,
        state,
        prompt,
        kwargs,
        request_id,
        event_sink,
    ) -> None:
        """Iterate over chat_model.stream and process chunks."""
        chat_model = self._owner._chat_model
        self._log_stream_prelude(chat_model, kwargs)
        stream_kwargs = strip_reasoning_for_forced_tool(
            chat_model, kwargs, prompt
        )
        if stream_kwargs is not kwargs:
            self._owner.logger.info(
                "[STREAM] Dropped reasoning params (restrictive "
                "tool_choice or tool-continuation turn)"
            )
        prompt = self._mask_prompt(prompt)
        chunk_count = 0
        visible_chunk_count = 0
        timing = StreamTiming()
        from airunner_services.cloud.llm.completion_choke import (
            stream_with_limiter,
        )
        for chunk in stream_with_limiter(
            chat_model, prompt,
            priority="live",
            **stream_kwargs,
        ):
            chunk_count += 1
            if self._owner._interrupted:
                break
            visible_chunk_count += self._run_stream_iteration(
                state, chunk, request_id, event_sink, timing
            )
        self._log_stream_summary(
            chunk_count, visible_chunk_count, state, timing
        )

    def _run_stream_iteration(
        self,
        state,
        chunk,
        request_id: Optional[str],
        event_sink,
        timing,
    ) -> int:
        """Process one chunk; return 1 when visibility toggled else 0."""
        had_visible = bool(state.streamed_content)
        self._process_chunk(state, chunk, request_id, event_sink)
        now_visible = bool(state.streamed_content)
        toggled = 1 if now_visible != had_visible else 0
        if now_visible:
            timing.record()
        return toggled

    def _process_chunk(
        self,
        state: StreamingState,
        chunk,
        request_id: Optional[str],
        event_sink,
    ) -> None:
        """Process one streamed chunk from the chat model."""
        chunk_message = getattr(chunk, "message", chunk)
        text = getattr(chunk_message, "content", "") or ""
        text = self._restore_chunk_pii(text)
        additional_kwargs = (
            getattr(chunk_message, "additional_kwargs", {}) or {}
        )
        reasoning_delta = (
            additional_kwargs.get("thinking_content")
            or additional_kwargs.get("reasoning_content")
            or additional_kwargs.get("reasoning")
        )
        chunk_tool_calls = getattr(chunk_message, "tool_calls", None)
        print_stream_debug(
            "node_functions.chunk", request_id=request_id, content=text,
            reasoning_content=reasoning_delta, tool_calls=chunk_tool_calls,
            in_thinking_block=state.in_thinking_block,
        )
        usage = getattr(chunk_message, "usage_metadata", None)
        if usage is not None:
            state.last_usage_metadata = usage
            self._owner.logger.info(
                "[STREAM_CHUNK] usage_metadata=%s", usage
            )
        state.last_chunk_message = chunk_message
        accumulate_chunk(state, chunk_message)
        if not text and not chunk_tool_calls and not reasoning_delta:
            return
        # Suppress the text content of a chunk that carries tool calls.
        # A tool-call message's text is model-internal scaffolding (some
        # models emit an incidental preamble alongside the call — e.g.
        # local GGUF/ollama models); streaming it to the user leaks
        # raw diagnostics before the real reply. Only the reasoning
        # delta is still routed (thinking block).
        if chunk_tool_calls:
            text = ""
        self._route_chunk_content(
            state, request_id, event_sink, text, reasoning_delta
        )

    def _restore_chunk_pii(self, text: str) -> str:
        """Restore PII placeholders before text reaches the user."""
        vault = getattr(self._owner, "_pii_vault", None)
        if vault is None or not text:
            return text
        try:
            from airunner_services.llm.pii.restorer import restore_text
            return restore_text(text, vault)
        except Exception:
            return text

    def _route_chunk_content(
        self,
        state,
        request_id: Optional[str],
        event_sink,
        text: str,
        reasoning_delta,
    ) -> None:
        """Route one chunk to thinking or visible-text handling."""
        th = self._thinking_helper
        if th.handle_reasoning_delta(state, request_id, event_sink,
                                     reasoning_delta, text):
            return
        if th.handle_thinking_open(state, request_id, event_sink, text):
            return
        if state.in_thinking_block:
            th.handle_thinking_block(state, request_id, event_sink, text)
            return
        text_to_stream = filter_tool_markup(state, text)
        text_to_stream = _strip_internal_diagnostics(text_to_stream)
        if text_to_stream:
            store_visible_text(state, self._owner, request_id, text_to_stream)

    def _mask_prompt(self, prompt):
        """Mask PII in LangChain messages before LLM egress."""
        vault = getattr(self._owner, "_pii_vault", None)
        if vault is None:
            return prompt
        from airunner_services.llm.pii.masker import (
            mask_langchain_messages,
        )
        return mask_langchain_messages(prompt, vault)

    def _log_stream_prelude(self, chat_model, kwargs) -> None:
        """Log the model configuration before streaming begins."""
        binding_kwargs = getattr(chat_model, "kwargs", {}) or {}
        bound_model = getattr(chat_model, "bound", chat_model)
        bound_model_kwargs = getattr(bound_model, "model_kwargs", {}) or {}
        self._owner.logger.info(
            "[STREAM] chat_model type=%s binding_kwargs_keys=%s "
            "binding_tool_choice=%r extra_body_in_kwargs=%r "
            "extra_body_in_binding=%r model_kwargs_keys=%s",
            type(chat_model).__name__,
            list(binding_kwargs.keys()),
            binding_kwargs.get("tool_choice"),
            (kwargs.get("extra_body") or {}).get("reasoning"),
            (binding_kwargs.get("extra_body") or {}).get("reasoning"),
            list(bound_model_kwargs.keys()),
        )

    def _log_stream_summary(
        self, chunk_count, visible_chunk_count, state, timing
    ) -> None:
        """Log the final stream statistics."""
        self._owner.logger.info(
            "[STREAM] done: chunks=%d visible=%d content_len=%d "
            "first_chunk_ms=%s max_gap_ms=%s total_ms=%s",
            chunk_count, visible_chunk_count, len(state.streamed_content),
            timing.first_chunk_ms(), timing.max_gap_ms(),
            timing.total_ms(),
        )
