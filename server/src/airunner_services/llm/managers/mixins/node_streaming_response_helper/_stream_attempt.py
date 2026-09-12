"""Retry / fallback decision logic for one streamed response.

``NodeStreamingAttemptMixin`` implements the retry-once-on-mid-stream-
cut policy and maps permanent client errors (exhausted API key),
live-lane exhaustion, and provider API errors to the appropriate
user-visible ``AIMessage``.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from airunner_services.llm.managers.mixins.node_streaming_response_helper._base import (
    _dedupe_finish_reason,
)
from airunner_services.llm.managers.mixins.node_streaming_state import (
    StreamingState,
)
from airunner_services.utils.network_retry import (
    extract_user_error_message,
    is_permanent_client_error,
    is_transient_network_error,
    mark_api_exhausted,
)


class NodeStreamingAttemptMixin:
    """Retry and fallback decision logic for one streamed response."""

    def _attempt_stream(
        self,
        prompt,
        kwargs,
        request_id: str | None,
        event_sink,
        *,
        _retry: bool = True,
    ) -> AIMessage | None:
        """Try one stream; retry once when the stream is cut mid-response."""
        state = StreamingState()
        try:
            self._run_stream_loop(
                state, prompt, kwargs, request_id, event_sink
            )
            self._thinking_helper.finalize_reasoning_delta(
                state, request_id, event_sink
            )
            if state.streamed_content or state.last_chunk_message:
                if self._warn_if_stream_ended_abnormally(
                    state, kwargs, _retry,
                ):
                    if _retry:
                        self._owner.logger.warning(
                            "Stream ended without finish_reason at %d "
                            "chars; retrying once",
                            sum(len(c) for c in state.streamed_content),
                        )
                        self._reset_and_signal(request_id, event_sink)
                        return self._attempt_stream(
                            prompt, kwargs, request_id, event_sink,
                            _retry=False,
                        )
                    self._owner.logger.warning(
                        "Stream ended without finish_reason after retry; "
                        "delivering partial message"
                    )
                return self._build_streamed_message(state, prompt)
            return self._fallback_empty_message()
        except Exception as exc:
            return self._handle_stream_error(
                state, exc, prompt, kwargs, request_id, event_sink,
                _retry,
            )

    def _handle_stream_error(
        self,
        state,
        exc: Exception,
        prompt,
        kwargs,
        request_id: str | None,
        event_sink,
        _retry: bool,
    ) -> AIMessage | None:
        """Decide the response for one streamed-call failure."""
        self._log_stream_error(exc)
        # Permanent client errors (401, 403, 404, etc.) will never
        # succeed on retry. Open the circuit breaker so background
        # tasks (interjection, reflection, curiosity) stop wasting
        # calls on an exhausted key, then re-raise so the worker's
        # error handler sends a system error message instead of a
        # conversational AIMessage that would trigger a client-side
        # retry loop.
        if is_permanent_client_error(exc):
            mark_api_exhausted(exc)
            raise
        if _retry and (
            state.streamed_content
            or is_transient_network_error(exc)
        ):
            self._owner.logger.warning(
                "Stream cut at %d chars; retrying",
                sum(len(c) for c in state.streamed_content))
            self._reset_and_signal(request_id, event_sink)
            return self._attempt_stream(
                prompt, kwargs, request_id, event_sink, _retry=False
            )
        if state.streamed_content:
            return self._build_streamed_message(state)
        if is_transient_network_error(exc):
            self._owner.logger.warning(
                "Network error after retry; "
                "propagating to error handler"
            )
            raise
        return self._error_message_for(exc)

    def _error_message_for(self, exc: Exception) -> AIMessage | None:
        """Map an API / live-lane error to a user-visible message."""
        user_msg = extract_user_error_message(exc)
        if user_msg:
            self._owner.logger.warning(
                "API error returned to user: %s", user_msg
            )
            return AIMessage(
                content=(
                    "An error occurred while contacting the model: "
                    + user_msg
                ),
                additional_kwargs={"error": "api_error"},
                tool_calls=[],
            )
        # Live-lane exhaustion: the distributed limiter couldn't
        # acquire a slot within the bounded wait window.  Surface
        # a user-visible message so the caller knows what happened
        # instead of silently returning None.
        from airunner_services.cloud.llm.completion_choke import (
            LiveLaneExhaustedError,
        )
        if isinstance(exc, LiveLaneExhaustedError):
            self._owner.logger.warning(
                "Live lane exhausted — returning busy message"
            )
            return AIMessage(
                content=(
                    "The model is currently busy — "
                    "please try again in a moment."
                ),
                additional_kwargs={"error": "capacity_exhausted"},
                tool_calls=[],
            )
        return None

    def _warn_if_stream_ended_abnormally(
        self,
        state,
        kwargs: dict,
        _retry: bool,
    ) -> bool:
        """Detect when a streaming response ends without a normal
        ``finish_reason: "stop"`` — network drop, provider disconnect,
        or mid-stream cut that is NOT the ``max_tokens`` ceiling.

        Returns True when the stream ended abnormally and should be
        retried by ``_attempt_stream`` (silent cut with no
        finish_reason, or ``finish_reason=length`` under the token
        ceiling).  Returns False for a normal ``stop`` / ``end_turn``
        ending.  Unlike ``_check_truncation`` (which runs inside
        ``_build_streamed_message`` and only logs), this runs before
        the message is built so the retry path in
        ``_attempt_stream`` can still fire when appropriate.
        """
        msg = getattr(state, "accumulated_message", None)
        if msg is None:
            return False
        metadata = getattr(msg, "response_metadata", None) or {}
        finish_reason = _dedupe_finish_reason(
            metadata.get("finish_reason", "")
        )
        token_usage = metadata.get("token_usage", {}) or {}
        completion_tokens = token_usage.get("completion_tokens", 0)

        if not finish_reason:
            self._owner.logger.warning(
                "[STREAM CUT] No finish_reason in final chunk — "
                "response may be truncated mid-stream. "
                "chars=%d tokens=%d",
                sum(len(c) for c in state.streamed_content),
                completion_tokens,
            )
            return True

        # "length" under the token ceiling is a genuine provider-side
        # truncation, distinct from hitting max_tokens (which is
        # logged separately by _check_truncation).
        if finish_reason == "length":
            requested = kwargs.get("max_tokens") or kwargs.get(
                "max_new_tokens",
            )
            if requested is None or completion_tokens < requested:
                self._owner.logger.warning(
                    "[STREAM CUT] finish_reason=length but only "
                    "%d / %s tokens — provider-side truncation, "
                    "not max_tokens ceiling",
                    completion_tokens,
                    requested or "?",
                )
                return True
        return False
