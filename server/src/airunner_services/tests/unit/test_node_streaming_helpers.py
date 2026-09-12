"""Unit tests for node_streaming_response_helpers.

Covers the tool-call markup filters, max-token set/restore, chunk
accumulation, role-preamble stripping, and the visible-text storage
path (including the BPE digit-boundary fix and the token-callback
error handling).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from airunner_services.llm.managers.mixins.node_streaming_response_helpers import (
    accumulate_chunk,
    filter_tool_markup,
    has_deepseek_tool_token,
    is_tool_call_end,
    is_tool_call_start,
    restore_max_tokens,
    set_request_max_tokens,
    store_visible_text,
    strip_leading_assistant_preamble,
)
from airunner_services.llm.managers.mixins.node_streaming_state import (
    StreamingState,
)


# ---------------------------------------------------------------------------
# Tool-call markup detection
# ---------------------------------------------------------------------------


def test_is_tool_call_start_react() -> None:
    assert is_tool_call_start("Action: search_web") is True
    assert is_tool_call_start("Action Input: {'q': 'x'}") is True


def test_is_tool_call_start_deepseek() -> None:
    assert is_tool_call_start("hi<｜tool▁calls｜>") is True
    assert is_tool_call_start("x<|tool") is True


def test_is_tool_call_start_false() -> None:
    assert is_tool_call_start("plain text") is False


def test_is_tool_call_end_variants() -> None:
    assert is_tool_call_end("<｜tool▁calls▁end｜>") is True
    assert is_tool_call_end("</tool_calls>") is True
    assert is_tool_call_end("DSML") is True


def test_is_tool_call_end_false() -> None:
    assert is_tool_call_end("plain") is False


def test_has_deepseek_tool_token() -> None:
    assert has_deepseek_tool_token("x</｜y") is True
    assert has_deepseek_tool_token("xDSMLy") is True
    assert has_deepseek_tool_token("tool_calls>") is True
    assert has_deepseek_tool_token("clean") is False


# ---------------------------------------------------------------------------
# max_tokens set/restore
# ---------------------------------------------------------------------------


def test_set_request_max_tokens_none() -> None:
    assert set_request_max_tokens(SimpleNamespace(), None) is None


def test_set_request_max_tokens_no_attribute() -> None:
    assert set_request_max_tokens(SimpleNamespace(), 100) is None


def test_set_request_max_tokens_sets_on_bound() -> None:
    bound = SimpleNamespace(max_tokens=10)
    model = SimpleNamespace(bound=bound)
    old = set_request_max_tokens(model, 200)
    assert old == 10
    assert bound.max_tokens == 200


def test_set_request_max_tokens_exception() -> None:
    class _Readonly:
        max_tokens = 1

        def __setattr__(self, name, value):
            raise ValueError("readonly")

    model = SimpleNamespace(bound=_Readonly())
    # bound.max_tokens setter raises → the try/except returns None.
    assert set_request_max_tokens(model, 5) is None


def test_restore_max_tokens_none() -> None:
    restore_max_tokens(SimpleNamespace(), None)  # no raise


def test_restore_max_tokens_restores() -> None:
    bound = SimpleNamespace(max_tokens=10)
    model = SimpleNamespace(bound=bound)
    restore_max_tokens(model, 10)
    assert bound.max_tokens == 10


def test_restore_max_tokens_bound_without_attribute() -> None:
    """A bound object without max_tokens falls back to the model."""
    bound = SimpleNamespace()  # no max_tokens attr
    model = SimpleNamespace(bound=bound)
    model.max_tokens = 5
    restore_max_tokens(model, 5)
    assert model.max_tokens == 5


def test_restore_max_tokens_exception_swallowed() -> None:
    class _Readonly:
        max_tokens = 1

        def __setattr__(self, name, value):
            raise ValueError("no")

    restore_max_tokens(SimpleNamespace(bound=_Readonly()), 5)  # no raise


# ---------------------------------------------------------------------------
# accumulate_chunk
# ---------------------------------------------------------------------------


def test_accumulate_chunk_first() -> None:
    state = StreamingState()
    chunk = AIMessage(content="a")
    accumulate_chunk(state, chunk)
    assert state.accumulated_message is chunk


def test_accumulate_chunk_second() -> None:
    from langchain_core.messages import AIMessageChunk

    state = StreamingState()
    first = AIMessageChunk(content="a")
    second = AIMessageChunk(content="b")
    accumulate_chunk(state, first)
    accumulate_chunk(state, second)
    # AIMessageChunk + AIMessageChunk concatenates content.
    assert state.accumulated_message.content == "ab"


def test_accumulate_chunk_exception_collects_tool_calls() -> None:
    state = StreamingState()
    chunk = AIMessage(
        content="x",
        tool_calls=[{"name": "f", "args": {}, "id": "1"}],
    )
    state.accumulated_message = "not a message"
    accumulate_chunk(state, chunk)
    assert state.collected_tool_calls


def test_accumulate_chunk_exception_no_tool_calls() -> None:
    """A + failure with no tool calls still swallows the exception."""
    state = StreamingState()
    chunk = AIMessage(content="x")  # no tool_calls
    state.accumulated_message = "not a message"
    accumulate_chunk(state, chunk)  # no raise, nothing collected
    assert state.collected_tool_calls == []


# ---------------------------------------------------------------------------
# filter_tool_markup
# ---------------------------------------------------------------------------


def test_filter_tool_markup_inside_block() -> None:
    state = StreamingState(in_tool_call_tag=True)
    assert filter_tool_markup(state, "text") == ""
    assert state.in_tool_call_tag is True


def test_filter_tool_markup_ends_block() -> None:
    state = StreamingState(in_tool_call_tag=True)
    assert filter_tool_markup(state, "x<｜tool▁calls▁end｜>") == ""
    assert state.in_tool_call_tag is False


def test_filter_tool_markup_starts_block() -> None:
    state = StreamingState()
    assert filter_tool_markup(state, "Action: f") == ""
    assert state.in_tool_call_tag is True


def test_filter_tool_markup_deepseek_token() -> None:
    state = StreamingState()
    assert filter_tool_markup(state, "xDSMLy") == ""


def test_filter_tool_markup_passthrough() -> None:
    state = StreamingState()
    assert filter_tool_markup(state, "clean text") == "clean text"


# ---------------------------------------------------------------------------
# strip_leading_assistant_preamble
# ---------------------------------------------------------------------------


def test_strip_prefix_variants() -> None:
    assert strip_leading_assistant_preamble("assistant: hi") == " hi"
    assert strip_leading_assistant_preamble("user\nhi") == "hi"
    assert strip_leading_assistant_preamble("human hello") == "hello"
    assert strip_leading_assistant_preamble("assistant\nhi") == "hi"


def test_strip_exact_role() -> None:
    assert strip_leading_assistant_preamble("assistant") == ""
    assert strip_leading_assistant_preamble("user") == ""


def test_strip_no_prefix() -> None:
    assert strip_leading_assistant_preamble("  hello") == "  hello"


# ---------------------------------------------------------------------------
# store_visible_text
# ---------------------------------------------------------------------------


def test_store_visible_text_appends_and_forwards() -> None:
    owner = SimpleNamespace(_token_callback=MagicMock(), logger=MagicMock())
    state = StreamingState()
    store_visible_text(state, owner, "req-1", "hello")
    assert state.streamed_content == ["hello"]
    assert state.has_streamed_content is True
    assert owner._streamed_content is True
    owner._token_callback.assert_called_once_with("hello")


def test_store_visible_text_strips_preamble_on_first() -> None:
    owner = SimpleNamespace(_token_callback=MagicMock(), logger=MagicMock())
    state = StreamingState()
    # "assistant: hi" matches the "assistant:" prefix → strips to " hi"
    # (the leading space after the colon is preserved).
    store_visible_text(state, owner, "req-1", "assistant: hi")
    assert state.streamed_content == [" hi"]
    owner._token_callback.assert_called_once_with(" hi")


def test_store_visible_text_empty_after_strip() -> None:
    owner = SimpleNamespace(_token_callback=MagicMock(), logger=MagicMock())
    state = StreamingState()
    store_visible_text(state, owner, "req-1", "assistant")
    assert state.streamed_content == []
    owner._token_callback.assert_not_called()


def test_store_visible_text_already_streamed_no_strip() -> None:
    """Once content has streamed, the preamble is NOT stripped again."""
    owner = SimpleNamespace(_token_callback=MagicMock(), logger=MagicMock())
    state = StreamingState(has_streamed_content=True, streamed_content=["x"])
    store_visible_text(state, owner, "req-1", "assistant: hi")
    assert state.streamed_content == ["x", "assistant: hi"]


def test_store_visible_text_digit_boundary_fix() -> None:
    owner = SimpleNamespace(_token_callback=MagicMock(), logger=MagicMock())
    state = StreamingState(streamed_content=["1"])
    store_visible_text(state, owner, "req-1", " 2")
    assert state.streamed_content == ["1", "2"]


def test_store_visible_text_keeps_space_before_word() -> None:
    owner = SimpleNamespace(_token_callback=MagicMock(), logger=MagicMock())
    state = StreamingState(streamed_content=["1"])
    store_visible_text(state, owner, "req-1", " occurrence")
    assert state.streamed_content == ["1", " occurrence"]


def test_store_visible_text_no_callback() -> None:
    owner = SimpleNamespace(_token_callback=None, logger=MagicMock())
    state = StreamingState()
    store_visible_text(state, owner, "req-1", "hi")
    assert state.streamed_content == ["hi"]


def test_store_visible_text_callback_error_logged() -> None:
    owner = SimpleNamespace(
        _token_callback=MagicMock(side_effect=RuntimeError("boom")),
        logger=MagicMock(),
    )
    state = StreamingState()
    store_visible_text(state, owner, "req-1", "hi")
    owner.logger.error.assert_called_once()
