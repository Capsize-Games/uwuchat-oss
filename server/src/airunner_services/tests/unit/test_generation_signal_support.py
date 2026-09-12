"""Unit tests for generation_signal_support streaming helpers.

Covers the assistant-preamble stripping, the streaming-token signal
emission, the thinking callback, the end-of-message emission, and the
mediator fallback for owners without a direct signal path.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from airunner_services.llm.llm_response import LLMResponse

from airunner_services.llm.managers.mixins.generation_signal_support import (
    _emit_token_signal,
    _handle_streaming_token,
    _is_assistant_preamble_only,
    _send_signal,
    _signal_mediator_fallback,
    _strip_leading_assistant_preamble,
    create_streaming_callback,
    create_thinking_callback,
    current_assistant_turn_index,
    emit_visible_response,
    send_end_of_message,
)


def _owner(**attrs) -> SimpleNamespace:
    defaults = {
        "_current_request_id": "req-1",
        "_call_chain_id": "chain-1",
        "logger": MagicMock(),
    }
    defaults.update(attrs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Preamble helpers
# ---------------------------------------------------------------------------


def test_is_assistant_preamble_only() -> None:
    assert _is_assistant_preamble_only("assistant") is True
    assert _is_assistant_preamble_only("Assistant:") is True
    assert _is_assistant_preamble_only("hello") is False


def test_strip_leading_assistant_preamble() -> None:
    assert _strip_leading_assistant_preamble("", "assistant\nhi") == "hi"
    assert _strip_leading_assistant_preamble("existing", "assistant hi") == "assistant hi"
    assert _strip_leading_assistant_preamble("", "assistant") == ""
    assert _strip_leading_assistant_preamble("", "hi") == "hi"


# ---------------------------------------------------------------------------
# current_assistant_turn_index
# ---------------------------------------------------------------------------


def test_current_assistant_turn_index() -> None:
    owner = SimpleNamespace(
        _workflow_manager=SimpleNamespace(_assistant_turn_index=3)
    )
    assert current_assistant_turn_index(owner) == 3


def test_current_assistant_turn_index_missing() -> None:
    assert current_assistant_turn_index(SimpleNamespace()) == 0


# ---------------------------------------------------------------------------
# _handle_streaming_token / _emit_token_signal
# ---------------------------------------------------------------------------


def test_handle_streaming_token_emits() -> None:
    owner = _owner(send_llm_text_streamed_signal=MagicMock())
    complete = [""]
    seq = [0]
    _handle_streaming_token("hi", owner, None, complete, seq)
    assert complete[0] == "hi"
    assert seq[0] == 1
    owner.send_llm_text_streamed_signal.assert_called_once()


def test_handle_streaming_token_strips_preamble() -> None:
    owner = _owner(send_llm_text_streamed_signal=MagicMock())
    complete = [""]
    seq = [0]
    _handle_streaming_token("assistant\nhi", owner, None, complete, seq)
    assert complete[0] == "hi"


def test_handle_streaming_token_empty_returns() -> None:
    """A token that strips to nothing returns without emitting."""
    owner = _owner(send_llm_text_streamed_signal=MagicMock())
    complete = [""]
    seq = [0]
    _handle_streaming_token("assistant", owner, None, complete, seq)
    assert complete[0] == ""
    owner.send_llm_text_streamed_signal.assert_not_called()


def test_handle_streaming_token_missing_request_id_warns() -> None:
    """A missing _current_request_id logs a warning but still emits."""
    owner = _owner(
        _current_request_id=None, send_llm_text_streamed_signal=MagicMock()
    )
    complete = [""]
    seq = [0]
    _handle_streaming_token("tok", owner, None, complete, seq)
    owner.logger.warning.assert_called_once()
    owner.send_llm_text_streamed_signal.assert_called_once()


def test_emit_token_signal_via_mediator_fallback() -> None:
    # Owner without send_llm_text_streamed_signal → _signal_mediator_fallback.
    owner = _owner()
    with patch(
        "airunner_services.llm.managers.mixins.generation_signal_support._signal_mediator_fallback"
    ) as fallback:
        _emit_token_signal(owner, None, "tok", [0])
    fallback.assert_called_once()


# ---------------------------------------------------------------------------
# _send_signal
# ---------------------------------------------------------------------------


def test_send_signal_via_owner_method() -> None:
    owner = _owner(send_llm_text_streamed_signal=MagicMock())
    _send_signal(owner, None, "msg")
    owner.send_llm_text_streamed_signal.assert_called_once()
    resp = owner.send_llm_text_streamed_signal.call_args[0][0]
    assert isinstance(resp, LLMResponse)
    assert resp.message == "msg"
    assert resp.request_id == "req-1"


def test_send_signal_mediator_fallback() -> None:
    owner = _owner()
    with patch(
        "airunner_services.llm.managers.mixins.generation_signal_support._signal_mediator_fallback"
    ) as fallback:
        _send_signal(owner, None, "msg")
    fallback.assert_called_once()


def test_signal_mediator_fallback_no_request_id() -> None:
    owner = _owner(_current_request_id=None)
    _signal_mediator_fallback(LLMResponse(message="x"))
    # No request_id → no emit; no raise.


def test_signal_mediator_fallback_emits() -> None:
    with patch(
        "airunner_services.utils.application.signal_mediator.SignalMediator"
    ) as mediator_cls:
        mediator = MagicMock()
        mediator_cls.return_value = mediator
        _signal_mediator_fallback(LLMResponse(message="x", request_id="r1"))
    mediator.emit_signal.assert_called_once()


# ---------------------------------------------------------------------------
# emit_visible_response
# ---------------------------------------------------------------------------


def test_emit_visible_response_emits_when_empty() -> None:
    owner = _owner(send_llm_text_streamed_signal=MagicMock())
    complete = [""]
    seq = [0]
    emit_visible_response(owner, None, "full", complete, seq)
    assert complete[0] == "full"
    assert seq[0] == 1


def test_emit_visible_response_skips_when_content() -> None:
    owner = _owner(send_llm_text_streamed_signal=MagicMock())
    complete = ["existing"]
    seq = [0]
    emit_visible_response(owner, None, "full", complete, seq)
    assert complete[0] == "existing"
    owner.send_llm_text_streamed_signal.assert_not_called()


def test_emit_visible_response_strips_preamble_only() -> None:
    owner = _owner(send_llm_text_streamed_signal=MagicMock())
    complete = ["assistant"]
    seq = [0]
    emit_visible_response(owner, None, "full", complete, seq)
    assert complete[0] == "full"
    owner.send_llm_text_streamed_signal.assert_called_once()
    resp = owner.send_llm_text_streamed_signal.call_args[0][0]
    assert resp.message == "full"


# ---------------------------------------------------------------------------
# create_streaming_callback / create_thinking_callback
# ---------------------------------------------------------------------------


def test_create_streaming_callback_forwards() -> None:
    owner = _owner(send_llm_text_streamed_signal=MagicMock())
    cb = create_streaming_callback(owner, None, [""], [0])
    cb("token")
    assert owner.send_llm_text_streamed_signal.call_count == 1


def test_create_thinking_callback_streaming() -> None:
    owner = _owner(send_llm_text_streamed_signal=MagicMock())
    cb = create_thinking_callback(owner, None, [0])
    cb("streaming", "reason")
    owner.send_llm_text_streamed_signal.assert_called_once()
    resp = owner.send_llm_text_streamed_signal.call_args[0][0]
    assert resp.message_type == "thinking"
    assert resp.message == "reason"


def test_create_thinking_callback_completed_skipped() -> None:
    owner = _owner(send_llm_text_streamed_signal=MagicMock())
    cb = create_thinking_callback(owner, None, [0])
    cb("completed", "full text")
    owner.send_llm_text_streamed_signal.assert_not_called()


# ---------------------------------------------------------------------------
# send_end_of_message
# ---------------------------------------------------------------------------


def test_send_end_of_message_emits_tools() -> None:
    owner = _owner(send_llm_text_streamed_signal=MagicMock())
    send_end_of_message(owner, None, [0], ["execute_command"], 1, 2, 3)
    resp = owner.send_llm_text_streamed_signal.call_args[0][0]
    assert resp.is_end_of_message is True
    assert resp.tools == ["execute_command"]
    assert resp.prompt_tokens == 1
    assert resp.completion_tokens == 2
    assert resp.total_tokens == 3
    assert resp.call_chain_id == "chain-1"
    assert resp.final_visible_message is None


def test_send_end_of_message_with_final_visible() -> None:
    owner = _owner(send_llm_text_streamed_signal=MagicMock())
    send_end_of_message(
        owner, None, [0], [], None, None, None,
        final_visible_message="full text",
    )
    resp = owner.send_llm_text_streamed_signal.call_args[0][0]
    assert resp.final_visible_message == "full text"


def test_send_end_of_message_missing_request_id_warns() -> None:
    """A missing _current_request_id logs a warning but still emits."""
    owner = _owner(
        _current_request_id=None, send_llm_text_streamed_signal=MagicMock()
    )
    send_end_of_message(owner, None, [0], [], None, None, None)
    owner.logger.warning.assert_called_once()
    owner.send_llm_text_streamed_signal.assert_called_once()
