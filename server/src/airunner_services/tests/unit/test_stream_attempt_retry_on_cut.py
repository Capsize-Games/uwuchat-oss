"""Unit tests for NodeStreamingAttemptMixin retry-on-silent-cut.

The agentic loop must not deliver a partial, tool-less reply when the
edge daemon cuts the stream mid-generation without a ``finish_reason``.
``_attempt_stream`` now retries once on a silent cut (no finish_reason)
or a ``finish_reason=length`` under the token ceiling, mirroring the
existing retry path for raised stream errors.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from airunner_services.llm.managers.mixins.node_streaming_state import (
    StreamingState,
)


def _owner() -> SimpleNamespace:
    """Build a minimal owner object with the attrs the mixin reads."""
    return SimpleNamespace(
        logger=MagicMock(),
        _reset_stream_state=MagicMock(),
    )


def _mixin(owner) -> SimpleNamespace:
    """Create a NodeStreamingAttemptMixin instance bound to *owner*."""
    from airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_attempt import (
        NodeStreamingAttemptMixin,
    )

    mixin = NodeStreamingAttemptMixin()
    mixin._owner = owner
    mixin._thinking_helper = MagicMock()
    # Sibling-mixin collaborators the composed class provides.
    mixin._fallback_empty_message = MagicMock(
        return_value=AIMessage(content="", tool_calls=[]),
    )
    return mixin


def _cut_state() -> StreamingState:
    """A state whose final chunk has no finish_reason (silent cut)."""
    state = StreamingState()
    state.streamed_content = ["Let me read the files "]
    state.accumulated_message = AIMessage(
        content="Let me read the files ",
        response_metadata={"finish_reason": ""},
    )
    state.last_chunk_message = state.accumulated_message
    return state


def _complete_state() -> StreamingState:
    """A state whose final chunk finished normally."""
    state = StreamingState()
    state.streamed_content = ["Done."]
    state.accumulated_message = AIMessage(
        content="Done.",
        response_metadata={"finish_reason": "stop"},
    )
    state.last_chunk_message = state.accumulated_message
    return state


def _apply_state(state: StreamingState, canned: StreamingState) -> None:
    """Copy *canned* into *state* so the mixin sees a full response."""
    state.streamed_content = list(canned.streamed_content)
    state.accumulated_message = canned.accumulated_message
    state.last_chunk_message = canned.last_chunk_message


def test_attempt_stream_retries_once_on_silent_cut() -> None:
    """A stream cut with no finish_reason retries and returns attempt 2."""
    owner = _owner()
    mixin = _mixin(owner)
    results = iter([_cut_state(), _complete_state()])

    def fake_run_stream_loop(state, *args, **kwargs) -> None:
        # Copy the canned state into the fresh StreamingState the
        # mixin created, so the mixin sees the cut then the complete
        # response on the second attempt.
        canned = next(results)
        _apply_state(state, canned)

    mixin._run_stream_loop = fake_run_stream_loop
    mixin._build_streamed_message = MagicMock(
        return_value=AIMessage(content="Done.", tool_calls=[]),
    )
    mixin._reset_and_signal = MagicMock()

    out = mixin._attempt_stream(
        "prompt", {}, "req-1", MagicMock(), _retry=True,
    )

    assert out is not None
    assert out.content == "Done."
    assert mixin._build_streamed_message.call_count == 1
    assert mixin._reset_and_signal.call_count == 1
    owner.logger.warning.assert_any_call(
        "Stream ended without finish_reason at %d chars; retrying once",
        22,
    )


def test_attempt_stream_delivers_partial_on_retry_cut() -> None:
    """After one retry, a second silent cut delivers the partial message."""
    owner = _owner()
    mixin = _mixin(owner)
    mixin._run_stream_loop = MagicMock(
        side_effect=lambda state, *a, **k: _apply_state(
            state, _cut_state(),
        )
    )
    mixin._build_streamed_message = MagicMock(
        return_value=AIMessage(content="partial", tool_calls=[]),
    )
    mixin._reset_and_signal = MagicMock()

    out = mixin._attempt_stream(
        "prompt", {}, "req-1", MagicMock(), _retry=True,
    )

    assert out is not None
    assert out.content == "partial"
    assert mixin._build_streamed_message.call_count == 1
    assert mixin._reset_and_signal.call_count == 1
    owner.logger.warning.assert_any_call(
        "Stream ended without finish_reason after retry; "
        "delivering partial message",
    )


def test_attempt_stream_no_retry_when_finished() -> None:
    """A normal stop finish_reason does not trigger a retry."""
    owner = _owner()
    mixin = _mixin(owner)
    mixin._run_stream_loop = MagicMock(
        side_effect=lambda state, *a, **k: _apply_state(
            state, _complete_state(),
        )
    )
    mixin._build_streamed_message = MagicMock(
        return_value=AIMessage(content="fine", tool_calls=[]),
    )
    mixin._reset_and_signal = MagicMock()

    out = mixin._attempt_stream(
        "prompt", {}, "req-1", MagicMock(), _retry=True,
    )

    assert out is not None
    assert out.content == "fine"
    assert mixin._build_streamed_message.call_count == 1
    assert mixin._reset_and_signal.call_count == 0
