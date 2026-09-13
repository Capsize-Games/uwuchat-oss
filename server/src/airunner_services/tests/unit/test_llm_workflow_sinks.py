"""Unit tests for llm_workflow_sinks.

Covers the MediatorSignalLLMWorkflowEventSink (tool-status / mood /
stream-reset emission, including the injected LLM-text-stream markers
and their exception paths) and the MediatorSignalLLMToolActionHandler
(signal resolution, legacy signal mapping, no-emitter handling).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from airunner_services.llm_workflow_sinks import (
    MediatorSignalLLMToolActionHandler,
    MediatorSignalLLMWorkflowEventSink,
)


def _emitter() -> MagicMock:
    """A signal emitter that records emit_signal calls."""
    return MagicMock()


def _sink(emitter) -> MediatorSignalLLMWorkflowEventSink:
    return MediatorSignalLLMWorkflowEventSink(emitter)


# ---------------------------------------------------------------------------
# MediatorSignalLLMWorkflowEventSink
# ---------------------------------------------------------------------------


def test_emit_tool_status_forwards_and_streams() -> None:
    emitter = _emitter()
    sink = _sink(emitter)
    payload = {
        "tool_id": "tc-1",
        "tool_name": "execute_command",
        "status": "completed",
        "details": "src/",
        "request_id": "req-1",
    }
    sink.emit_tool_status(payload)

    # Mediator signal emitted with the raw payload.
    emitter.emit_signal.assert_any_call(
        __import__("airunner_services.contract_enums", fromlist=["SignalCode"]).SignalCode.LLM_TOOL_STATUS_SIGNAL,
        payload,
    )
    # Stream injection emitted with a tool_status LLMResponse.
    from airunner_services.contract_enums import SignalCode

    stream_calls = [
        c for c in emitter.emit_signal.call_args_list
        if c[0][0] is SignalCode.LLM_TEXT_STREAMED_SIGNAL
    ]
    assert len(stream_calls) == 1
    response = stream_calls[0][0][1]["response"]
    assert response.message_type == "tool_status"
    assert response.request_id == "req-1"
    import json as _json

    body = _json.loads(response.message)
    assert body["tool_name"] == "execute_command"
    assert body["status"] == "completed"


def test_emit_tool_status_stream_exception_is_silent() -> None:
    emitter = _emitter()
    sink = _sink(emitter)
    payload = {"tool_id": "tc-1", "request_id": "req-1"}

    # The first _emit (signal path) succeeds; the second (stream
    # injection inside _emit_tool_status_stream) raises and is swallowed.
    sink._emit = MagicMock(side_effect=[None, RuntimeError("boom")])
    sink.emit_tool_status(payload)


def test_emit_thinking_forwards_signal() -> None:
    emitter = _emitter()
    sink = _sink(emitter)
    sink.emit_thinking({"status": "started"})
    from airunner_services.contract_enums import SignalCode

    emitter.emit_signal.assert_called_once_with(
        SignalCode.LLM_THINKING_SIGNAL, {"status": "started"}
    )


def test_emit_bot_mood_forwards_and_streams() -> None:
    emitter = _emitter()
    sink = _sink(emitter)
    payload = {
        "mood": "happy",
        "emoji": "😊",
        "kaomoji": "(＾▽＾)",
        "request_id": "req-1",
    }
    sink.emit_bot_mood(payload)

    from airunner_services.contract_enums import SignalCode

    emitter.emit_signal.assert_any_call(SignalCode.BOT_MOOD_UPDATED, payload)
    stream_calls = [
        c for c in emitter.emit_signal.call_args_list
        if c[0][0] is SignalCode.LLM_TEXT_STREAMED_SIGNAL
    ]
    assert len(stream_calls) == 1
    response = stream_calls[0][0][1]["response"]
    assert response.message_type == "mood"
    import json as _json

    body = _json.loads(response.message)
    assert body["mood"] == "happy"
    assert body["emoji"] == "😊"


def test_emit_mood_stream_defaults() -> None:
    emitter = _emitter()
    sink = _sink(emitter)
    sink._emit_mood_stream({})
    from airunner_services.contract_enums import SignalCode

    stream_calls = [
        c for c in emitter.emit_signal.call_args_list
        if c[0][0] is SignalCode.LLM_TEXT_STREAMED_SIGNAL
    ]
    assert len(stream_calls) == 1
    response = stream_calls[0][0][1]["response"]
    import json as _json

    body = _json.loads(response.message)
    assert body["mood"] == "neutral"
    assert body["emoji"] == "😐"
    assert body["kaomoji"] == "(｡◕ᴗ◕｡)"


def test_emit_mood_stream_exception_logged() -> None:
    emitter = _emitter()
    sink = _sink(emitter)
    sink._emit = MagicMock(side_effect=RuntimeError("boom"))
    with patch(
        "airunner_services.llm_workflow_sinks._logger"
    ) as mock_logger:
        sink._emit_mood_stream({})
    mock_logger.exception.assert_called_once()


def test_emit_stream_reset_forwards() -> None:
    emitter = _emitter()
    sink = _sink(emitter)
    sink.emit_stream_reset("req-9")

    from airunner_services.contract_enums import SignalCode

    stream_calls = [
        c for c in emitter.emit_signal.call_args_list
        if c[0][0] is SignalCode.LLM_TEXT_STREAMED_SIGNAL
    ]
    assert len(stream_calls) == 1
    response = stream_calls[0][0][1]["response"]
    assert response.message_type == "stream_reset"
    assert response.request_id == "req-9"


def test_emit_stream_reset_exception_is_silent() -> None:
    emitter = _emitter()
    sink = _sink(emitter)
    sink._emit = MagicMock(side_effect=RuntimeError("boom"))
    with patch(
        "airunner_services.llm_workflow_sinks._logger"
    ):
        sink.emit_stream_reset("req-9")
    # Exception swallowed — no raise.


def test_emit_noop_when_emitter_not_callable() -> None:
    sink = MediatorSignalLLMWorkflowEventSink(MagicMock())
    sink._signal_emitter = object()  # no emit_signal attribute
    sink._emit(__import__("airunner_services.contract_enums", fromlist=["SignalCode"]).SignalCode.LLM_TOOL_STATUS_SIGNAL, {})
    # No raise; nothing emitted.


# ---------------------------------------------------------------------------
# MediatorSignalLLMToolActionHandler
# ---------------------------------------------------------------------------


def test_handle_action_maps_tool_action() -> None:
    emitter = _emitter()
    handler = MediatorSignalLLMToolActionHandler(emitter)
    from airunner_services.contract_enums import SignalCode

    result = handler.handle_action("clear_conversation", {"a": 1})
    assert result is True
    emitter.emit_signal.assert_called_once_with(
        SignalCode.LLM_CLEAR_HISTORY_SIGNAL, {"a": 1}
    )


def test_handle_action_returns_false_without_emitter() -> None:
    handler = MediatorSignalLLMToolActionHandler(object())
    assert handler.handle_action("clear_conversation", {}) is False


def test_handle_action_returns_false_unknown_action() -> None:
    emitter = _emitter()
    handler = MediatorSignalLLMToolActionHandler(emitter)
    assert handler.handle_action("does_not_exist", {}) is False
    emitter.emit_signal.assert_not_called()


def test_handle_action_legacy_signal() -> None:
    emitter = _emitter()
    handler = MediatorSignalLLMToolActionHandler(emitter)
    from airunner_services.contract_enums import SignalCode

    result = handler.handle_action(
        "emit_signal",
        {"signal_name": "BOT_MOOD_UPDATED", "data": {"mood": "happy"}},
    )
    assert result is True
    emitter.emit_signal.assert_called_once_with(
        SignalCode.BOT_MOOD_UPDATED, {"mood": "happy"}
    )


def test_legacy_signal_missing_name() -> None:
    handler = MediatorSignalLLMToolActionHandler(MagicMock())
    assert handler._legacy_signal({}) == (None, {})


def test_legacy_signal_unknown_name() -> None:
    handler = MediatorSignalLLMToolActionHandler(MagicMock())
    code, payload = handler._legacy_signal({"signal_name": "NOT_A_SIGNAL"})
    assert code is None
    assert payload == {"signal_name": "NOT_A_SIGNAL"}


def test_legacy_signal_non_dict_data() -> None:
    handler = MediatorSignalLLMToolActionHandler(MagicMock())
    from airunner_services.contract_enums import SignalCode

    code, payload = handler._legacy_signal(
        {"signal_name": "BOT_MOOD_UPDATED", "data": "string"}
    )
    assert code is SignalCode.BOT_MOOD_UPDATED
    assert payload == {}
