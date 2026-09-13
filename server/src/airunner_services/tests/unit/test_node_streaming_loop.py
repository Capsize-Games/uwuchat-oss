"""Unit tests for NodeStreamingLoopMixin.

Covers the chunk-processing loop, the tool-call text suppression
(critical for the execute_command-output bug — a tool-call chunk's
text must never leak to the user), PII restore/mask paths, and
thinking-block routing.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop import (
    _strip_internal_diagnostics,
)
from airunner_services.llm.managers.mixins.node_streaming_state import (
    StreamingState,
)
from airunner_services.llm.managers.mixins.node_streaming_timing import (
    StreamTiming,
)


def _owner(**attrs) -> SimpleNamespace:
    """Build a minimal owner object with the attrs the mixin reads."""
    defaults = {
        "_pii_vault": None,
        "_interrupted": False,
        "logger": MagicMock(),
        "_token_callback": None,
        "_chat_model": SimpleNamespace(),
    }
    defaults.update(attrs)
    return SimpleNamespace(**defaults)


def _mixin(owner) -> SimpleNamespace:
    """Create a NodeStreamingLoopMixin instance bound to *owner*."""
    from airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop import (
        NodeStreamingLoopMixin,
    )

    mixin = NodeStreamingLoopMixin()
    mixin._owner = owner
    mixin._thinking_helper = MagicMock()
    return mixin


def _chunk(content: str = "", tool_calls=None, **kwargs) -> AIMessage:
    """Build an AIMessage chunk with optional tool calls."""
    return AIMessage(
        content=content,
        tool_calls=tool_calls or [],
        additional_kwargs=kwargs,
    )


# ---------------------------------------------------------------------------
# _strip_internal_diagnostics
# ---------------------------------------------------------------------------


def test_strip_internal_diagnostics_empty_text() -> None:
    assert _strip_internal_diagnostics("") == ""


def test_strip_internal_diagnostics_removes_markers() -> None:
    text = (
        "The model attempted a tool-based response but did not produce "
        "a final reply. No changes were applied. hello"
    )
    assert "No changes were applied" not in _strip_internal_diagnostics(text)
    assert "hello" in _strip_internal_diagnostics(text)


def test_strip_internal_diagnostics_plain_text_unchanged() -> None:
    assert _strip_internal_diagnostics("plain reply") == "plain reply"


# ---------------------------------------------------------------------------
# _run_stream_iteration / _process_chunk
# ---------------------------------------------------------------------------


def test_process_chunk_streams_visible_text() -> None:
    """A plain text chunk flows through to store_visible_text."""
    owner = _owner()
    mixin = _mixin(owner)
    mixin._thinking_helper = MagicMock()
    mixin._thinking_helper.handle_reasoning_delta.return_value = False
    mixin._thinking_helper.handle_thinking_open.return_value = False
    state = StreamingState()

    with patch(
        "airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop.store_visible_text"
    ) as store:
        mixin._process_chunk(state, _chunk(content="hello world"), "req-1", None)

    store.assert_called_once()
    text = store.call_args[0][3]
    assert "hello world" in text


def test_process_chunk_suppresses_tool_call_text() -> None:
    """A chunk carrying tool_calls has its text blanked before routing.

    This is the execute_command-output bug path: the model's incidental
    preamble must not be streamed; the tool result is delivered via a
    separate tool_status delta, never as visible text here.
    """
    owner = _owner()
    mixin = _mixin(owner)
    state = StreamingState()
    tool_chunk = _chunk(
        content="I will run the command now",
        tool_calls=[{"name": "execute_command", "args": {}, "id": "tc-1"}],
    )

    with patch(
        "airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop.store_visible_text"
    ) as store:
        mixin._process_chunk(state, tool_chunk, "req-1", None)

    for call in store.call_args_list:
        assert "I will run" not in call.args[3]


def test_process_chunk_empty_chunk_returns_early() -> None:
    """A chunk with no text, tool calls, or reasoning is a no-op."""
    owner = _owner()
    mixin = _mixin(owner)
    state = StreamingState()

    with patch(
        "airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop.store_visible_text"
    ) as store:
        mixin._process_chunk(state, _chunk(), "req-1", None)

    store.assert_not_called()


def test_process_chunk_usage_metadata_is_recorded() -> None:
    """usage_metadata on a chunk is stored and logged."""
    from langchain_core.messages import AIMessageChunk

    owner = _owner()
    mixin = _mixin(owner)
    mixin._thinking_helper = MagicMock()
    mixin._thinking_helper.handle_reasoning_delta.return_value = False
    mixin._thinking_helper.handle_thinking_open.return_value = False
    state = StreamingState()
    usage = {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }
    chunk = AIMessageChunk(content="x", usage_metadata=usage)

    mixin._process_chunk(state, chunk, "req-1", None)

    # _process_chunk stashes the usage metadata on the last chunk
    # message (not on the StreamingState dataclass).
    assert state.last_chunk_message.usage_metadata == usage
    owner.logger.info.assert_called()


def test_process_chunk_reasoning_delta_only() -> None:
    """A chunk with only reasoning (no text) routes through thinking."""
    owner = _owner()
    mixin = _mixin(owner)
    state = StreamingState()
    chunk = _chunk(content="", thinking_content="reasoning text")

    with patch(
        "airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop.store_visible_text"
    ) as store:
        mixin._process_chunk(state, chunk, "req-1", None)
    mixin._thinking_helper.handle_reasoning_delta.assert_called_once()
    store.assert_not_called()


def test_run_stream_iteration_toggles_visibility() -> None:
    """Visibility toggling drives the returned count and timing record."""
    owner = _owner()
    mixin = _mixin(owner)
    state = StreamingState()
    timing = StreamTiming()

    # _process_chunk appends to streamed_content when visible.
    def _fake_process(_state, _chunk, _req, _sink):
        _state.streamed_content.append("x")

    with patch.object(mixin, "_process_chunk", side_effect=_fake_process):
        # First chunk turns visibility on → toggled == 1
        assert mixin._run_stream_iteration(
            state, _chunk(content="a"), "req-1", None, timing
        ) == 1
        # Second chunk keeps visibility on → toggled == 0
        assert mixin._run_stream_iteration(
            state, _chunk(content="b"), "req-1", None, timing
        ) == 0


def test_run_stream_loop_full_flow() -> None:
    """The loop drives chunks through the limiter and logs a summary."""
    owner = _owner()
    mixin = _mixin(owner)
    state = StreamingState()

    chunks = [
        _chunk(content="one"),
        _chunk(content=" two"),
        _chunk(content="", tool_calls=[{"name": "f", "args": {}, "id": "1"}]),
    ]
    with patch(
        "airunner_services.cloud.llm.completion_choke.stream_with_limiter",
        return_value=iter(chunks),
    ), patch.object(mixin, "_log_stream_prelude") as prelude, patch.object(
        mixin, "_log_stream_summary"
    ) as summary:
        mixin._run_stream_loop(state, [], {}, "req-1", None)

    prelude.assert_called_once()
    summary.assert_called_once()


def test_run_stream_loop_interrupt_breaks() -> None:
    """An interrupted owner stops the loop after the first chunk."""
    owner = _owner(_interrupted=True)
    mixin = _mixin(owner)
    state = StreamingState()

    with patch(
        "airunner_services.cloud.llm.completion_choke.stream_with_limiter",
        return_value=iter([_chunk(content="a"), _chunk(content="b")]),
    ), patch.object(mixin, "_log_stream_prelude") as prelude, patch.object(
        mixin, "_log_stream_summary"
    ) as summary:
        mixin._run_stream_loop(state, [], {}, "req-1", None)

    prelude.assert_called_once()
    summary.assert_called_once()


def test_run_stream_loop_dropped_reasoning_params() -> None:
    """When reasoning params are stripped, the owner logs a notice."""
    owner = _owner()
    mixin = _mixin(owner)
    state = StreamingState()

    original_kwargs = {"extra_body": {"reasoning": True}}
    stripped = {"extra_body": {}}

    with patch(
        "airunner_services.cloud.llm.completion_choke.stream_with_limiter",
        return_value=iter([]),
    ), patch(
        "airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop.strip_reasoning_for_forced_tool",
        return_value=stripped,
    ), patch.object(mixin, "_log_stream_prelude"), patch.object(
        mixin, "_log_stream_summary"
    ):
        mixin._run_stream_loop(state, [], original_kwargs, "req-1", None)

    owner.logger.info.assert_any_call(
        "[STREAM] Dropped reasoning params (restrictive "
        "tool_choice or tool-continuation turn)"
    )


# ---------------------------------------------------------------------------
# _restore_chunk_pii / _mask_prompt
# ---------------------------------------------------------------------------


def test_restore_chunk_pii_without_vault() -> None:
    """No vault → text returned unchanged."""
    owner = _owner()
    mixin = _mixin(owner)
    assert mixin._restore_chunk_pii("hi") == "hi"


def test_restore_chunk_pii_with_vault() -> None:
    """With a vault, restore_text is invoked."""
    owner = _owner(_pii_vault=MagicMock())
    mixin = _mixin(owner)
    with patch(
        "airunner_services.llm.pii.restorer.restore_text",
        return_value="restored",
    ):
        assert mixin._restore_chunk_pii("[PII]") == "restored"


def test_restore_chunk_pii_exception_returns_original() -> None:
    """A failing restore falls back to the original text."""
    owner = _owner(_pii_vault=MagicMock())
    mixin = _mixin(owner)
    with patch(
        "airunner_services.llm.pii.restorer.restore_text",
        side_effect=RuntimeError("boom"),
    ):
        assert mixin._restore_chunk_pii("[PII]") == "[PII]"


def test_mask_prompt_without_vault() -> None:
    """No vault → prompt returned unchanged."""
    owner = _owner()
    mixin = _mixin(owner)
    prompt = [{"role": "user", "content": "hi"}]
    assert mixin._mask_prompt(prompt) is prompt


def test_mask_prompt_with_vault() -> None:
    """With a vault, mask_langchain_messages is invoked."""
    owner = _owner(_pii_vault=MagicMock())
    mixin = _mixin(owner)
    with patch(
        "airunner_services.llm.pii.masker.mask_langchain_messages",
        return_value="masked",
    ):
        assert mixin._mask_prompt(["x"]) == "masked"


# ---------------------------------------------------------------------------
# _route_chunk_content / thinking helpers
# ---------------------------------------------------------------------------


def test_route_chunk_content_reasoning_delta_short_circuits() -> None:
    """handle_reasoning_delta True returns before visible routing."""
    owner = _owner()
    mixin = _mixin(owner)
    mixin._thinking_helper = MagicMock()
    mixin._thinking_helper.handle_reasoning_delta.return_value = True
    state = StreamingState()

    with patch(
        "airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop.store_visible_text"
    ) as store:
        mixin._route_chunk_content(state, "req-1", None, "text", "reason")
    store.assert_not_called()


def test_route_chunk_content_thinking_open() -> None:
    """handle_thinking_open True returns before visible routing."""
    owner = _owner()
    mixin = _mixin(owner)
    mixin._thinking_helper = MagicMock()
    mixin._thinking_helper.handle_reasoning_delta.return_value = False
    mixin._thinking_helper.handle_thinking_open.return_value = True
    state = StreamingState()

    with patch(
        "airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop.store_visible_text"
    ) as store:
        mixin._route_chunk_content(state, "req-1", None, "text", None)
    store.assert_not_called()


def test_route_chunk_content_thinking_block() -> None:
    """Inside a thinking block, chunks go to the thinking handler."""
    owner = _owner()
    mixin = _mixin(owner)
    mixin._thinking_helper = MagicMock()
    mixin._thinking_helper.handle_reasoning_delta.return_value = False
    mixin._thinking_helper.handle_thinking_open.return_value = False
    state = StreamingState(in_thinking_block=True)

    with patch(
        "airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop.store_visible_text"
    ) as store:
        mixin._route_chunk_content(state, "req-1", None, "think", None)
    mixin._thinking_helper.handle_thinking_block.assert_called_once()
    store.assert_not_called()


def test_route_chunk_content_visible_text_filtered() -> None:
    """Visible text passes through markup filter and diagnostics strip."""
    owner = _owner()
    mixin = _mixin(owner)
    mixin._thinking_helper = MagicMock()
    mixin._thinking_helper.handle_reasoning_delta.return_value = False
    mixin._thinking_helper.handle_thinking_open.return_value = False
    state = StreamingState()

    with patch(
        "airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop.store_visible_text"
    ) as store, patch(
        "airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop.filter_tool_markup",
        return_value="clean",
    ):
        mixin._route_chunk_content(state, "req-1", None, "raw", None)

    store.assert_called_once()
    assert store.call_args[0][3] == "clean"


def test_route_chunk_content_empty_text_after_filter() -> None:
    """Filtered-to-empty text never reaches store_visible_text."""
    owner = _owner()
    mixin = _mixin(owner)
    mixin._thinking_helper = MagicMock()
    mixin._thinking_helper.handle_reasoning_delta.return_value = False
    mixin._thinking_helper.handle_thinking_open.return_value = False
    state = StreamingState()

    with patch(
        "airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop.store_visible_text"
    ) as store, patch(
        "airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop.filter_tool_markup",
        return_value="",
    ):
        mixin._route_chunk_content(state, "req-1", None, "raw", None)
    store.assert_not_called()


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------


def test_log_stream_prelude_and_summary() -> None:
    """Both log helpers emit through owner.logger without raising."""
    owner = _owner()
    mixin = _mixin(owner)
    mixin._log_stream_prelude(SimpleNamespace(), {"extra_body": {}})
    mixin._log_stream_summary(1, 1, StreamingState(), StreamTiming())
    assert owner.logger.info.call_count == 2
