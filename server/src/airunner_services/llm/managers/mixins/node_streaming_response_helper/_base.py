"""Entry point, max-token handling, and pipeline config for the
streaming-response helper.

``NodeStreamingResponseHelperBase`` owns the public entry point
(``generate_streaming_response``), the max-token override around the
stream, and the small accessors shared by the stage mixins.  The
stage-specific logic lives in the sibling modules:

- ``_stream_attempt`` — retry / fallback decision logic
- ``_stream_loop`` — chunk iteration and per-chunk processing
- ``_stream_message`` — final message construction, truncation checks
- ``_stream_usage`` — token-usage recording
"""

from __future__ import annotations

from typing import Dict, Optional

from langchain_core.messages import AIMessage

from airunner_services.llm.managers.mixins.node_streaming_response_helpers import (
    restore_max_tokens,
    set_request_max_tokens,
)
from airunner_services.llm.managers.mixins.node_streaming_state import (
    StreamingState,
)
from airunner_services.llm.managers.mixins.node_streaming_thinking_helper import (
    NodeStreamingThinkingHelper,
)
from airunner_services.llm_workflow_events import (
    resolve_llm_workflow_event_sink,
)
from airunner_services.utils.network_retry import (
    is_transient_network_error,
    log_network_error_diagnostic,
)


def _dedupe_finish_reason(raw: str) -> str:
    """Deduplicate a finish_reason that was concatenated across chunks.

    LangChain's AIMessage merge may duplicate ``finish_reason`` when
    multiple chunks carry the same terminal value (e.g. ``"stopstop"``
    instead of ``"stop"``).  Take the first half if the string appears
    duplicated, otherwise return as-is.
    """
    if not raw or len(raw) < 2:
        return raw
    half = len(raw) // 2
    if raw[:half] == raw[half:]:
        return raw[:half]
    return raw


class NodeStreamingResponseHelperBase:
    """Entry point and shared state for the streaming-response helper."""

    def __init__(self, owner) -> None:
        """Store the owning workflow manager."""
        self._owner = owner
        self._thinking_helper = NodeStreamingThinkingHelper(self)

    def generate_streaming_response(
        self,
        formatted_prompt,
        generation_kwargs: Dict,
    ) -> Optional[AIMessage]:
        """Generate one streamed response, retrying once on a
        mid-stream cut."""
        event_sink = resolve_llm_workflow_event_sink(self._owner)
        request_id = getattr(self._owner, "_current_request_id", None)
        requested = (
            generation_kwargs.get("max_new_tokens")
            or generation_kwargs.get("max_tokens")
        )
        if requested is None:
            requested = self._pipeline_max_tokens()
        self._active_max_tokens = requested
        original = self._set_request_max_tokens(requested)
        try:
            return self._attempt_stream(
                formatted_prompt, generation_kwargs, request_id, event_sink
            )
        finally:
            self._restore_max_tokens(original)

    def _log_stream_error(self, exc: Exception) -> None:
        """Log one stream error at the appropriate level."""
        if is_transient_network_error(exc):
            log_network_error_diagnostic(
                self._owner.logger,
                "Error during streamed model call",
                exc,
            )
        else:
            self._owner.logger.warning(
                "Error during streamed model call: %s", exc
            )

    def _reset_and_signal(
        self, request_id: Optional[str], event_sink
    ) -> None:
        """Reset accumulated response state and signal the client."""
        try:
            reset_fn = getattr(self._owner, "_reset_stream_state", None)
            if callable(reset_fn):
                reset_fn()
            event_sink.emit_stream_reset(request_id)
        except Exception:
            pass

    def _set_request_max_tokens(
        self, requested: Optional[int]
    ) -> Optional[int]:
        """Temporarily set max_tokens on the chat model, returning old."""
        return set_request_max_tokens(self._owner._chat_model, requested)

    def _restore_max_tokens(self, original: Optional[int]) -> None:
        """Restore the chat model's original max_tokens."""
        restore_max_tokens(self._owner._chat_model, original)

    def _pipeline_max_tokens(self) -> Optional[int]:
        """Return the ``max_tokens`` value from the pipeline config
        for the current pipeline key, or ``None`` when unavailable."""
        phase = getattr(self._owner, "_current_node_phase", "DIALOGUE")
        pipeline_key = (
            "RESPONSE" if phase == "RESPONSE" else "DIALOGUE"
        )
        try:
            from airunner_services.llm.pipeline_loader import (
                pipeline_config,
            )
            cfg = pipeline_config(pipeline_key)
            return cfg.get("max_tokens")
        except Exception:
            return None
