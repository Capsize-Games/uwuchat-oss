"""Unit tests for ToolExecutionStatusMixin status emission.

Covers ``_sanitize_tool_functions`` (fallback docstrings),
``_emit_starting_status`` / ``_emit_completed_status`` (tool-status
payloads pushed through the workflow event sink), and
``_maybe_restore_mood_state`` (update_mood payload restore +
re-emission).  Exercises every branch, including the exception paths.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.messages import ToolMessage

from airunner_services.llm.managers.mixins.tool_execution_mixin._details import (
    ToolExecutionDetailsMixin,
)
from airunner_services.llm.managers.mixins.tool_execution_mixin._status import (
    ToolExecutionStatusMixin,
)


class _TestMixin(ToolExecutionStatusMixin, ToolExecutionDetailsMixin):
    """Combined mixin so _extract_* helpers resolve on the instance."""


class _MixinHost:
    """Minimal owner that provides every attribute the mixin reads."""

    def __init__(self) -> None:
        self._tools = []
        self._executed_tools = []
        self._conversation_id = 42
        self._current_request_id = "req-1"
        self._event_sink = MagicMock()
        self.logger = MagicMock()


def _host_with_tools(tools: list) -> _MixinHost:
    """Return a host whose _tools list contains *tools*."""
    host = _MixinHost()
    host._tools = tools
    return host


def _mixin(host: _MixinHost) -> _TestMixin:
    """Build a mixin instance bound to *host*'s attributes."""
    mixin = _TestMixin()
    mixin.__dict__.update(host.__dict__)
    return mixin


def _make_tool(name: str, doc: str | None = None) -> SimpleNamespace:
    """Build a bare tool object with optional docstring + __name__."""
    return SimpleNamespace(
        name=name, description=f"{name} desc", __doc__=doc, __name__=name,
    )


# ---------------------------------------------------------------------------
# _sanitize_tool_functions
# ---------------------------------------------------------------------------


def test_sanitize_adds_docstring_for_undocumented_tool() -> None:
    """A tool without a docstring gets a fallback from its description."""
    tool = _make_tool("fetch_thing", doc=None)
    host = _host_with_tools([tool])
    mixin = _mixin(host)

    mixin._sanitize_tool_functions()

    assert tool.__doc__ == "fetch_thing desc"
    host.logger.debug.assert_called_once()


def test_sanitize_uses_name_when_no_description() -> None:
    """Fallback docstring uses the tool name when description is missing."""
    tool = SimpleNamespace(
        name="bare_tool", description=None, __doc__=None, __name__="bare_tool",
    )
    mixin = _mixin(_host_with_tools([tool]))

    mixin._sanitize_tool_functions()

    assert "bare_tool" in tool.__doc__


def test_sanitize_skips_documented_tools() -> None:
    """A tool that already has a docstring is left untouched."""
    tool = _make_tool("documented_tool", doc="already documented")
    host = _host_with_tools([tool])
    mixin = _mixin(host)

    mixin._sanitize_tool_functions()

    assert tool.__doc__ == "already documented"
    host.logger.debug.assert_not_called()


# ---------------------------------------------------------------------------
# _emit_starting_status
# ---------------------------------------------------------------------------


def test_emit_starting_status_pushes_payload() -> None:
    """Starting status forwards name/args/query through the event sink."""
    host = _MixinHost()
    host._signal_emitter = MagicMock()
    mixin = _mixin(host)

    tool_calls = [
        {"name": "execute_command", "args": {"command": "ls"}, "id": "tc-1"},
        {"name": "search_web", "args": {"query": "climate news"}, "id": "tc-2"},
    ]

    mixin._emit_starting_status(tool_calls)

    assert host._executed_tools == ["execute_command", "search_web"]
    assert host._event_sink.emit_tool_status.call_count == 2
    first = host._event_sink.emit_tool_status.call_args_list[0][0][0]
    assert first["tool_id"] == "tc-1"
    assert first["tool_name"] == "execute_command"
    assert first["query"] == "{'command': 'ls'}"
    assert first["status"] == "starting"
    assert first["conversation_id"] == 42
    assert first["request_id"] == "req-1"
    second = host._event_sink.emit_tool_status.call_args_list[1][0][0]
    assert second["query"] == "climate news"


def test_emit_starting_status_unknown_tool_uses_defaults() -> None:
    """Missing name/args/id degrade to safe defaults."""
    host = _MixinHost()
    mixin = _mixin(host)

    mixin._emit_starting_status([{}])

    assert host._executed_tools == ["unknown"]
    payload = host._event_sink.emit_tool_status.call_args[0][0]
    assert payload["tool_id"] == ""
    assert payload["tool_name"] == "unknown"
    assert payload["query"] == "{}"


def test_emit_starting_status_empty_tool_calls() -> None:
    """An empty tool-call list emits nothing and returns."""
    host = _MixinHost()
    mixin = _mixin(host)

    mixin._emit_starting_status([])

    host._event_sink.emit_tool_status.assert_not_called()


# ---------------------------------------------------------------------------
# _emit_completed_status
# ---------------------------------------------------------------------------


def test_emit_completed_status_for_tool_message() -> None:
    """A matching ToolMessage yields a completed payload with details.

    The tool result must also be pushed into the text stream via
    _emit_tool_result_stream so the WebSocket always receives it.
    """
    host = _MixinHost()
    host._find_matching_tool_call = MagicMock(
        return_value={
            "name": "execute_command",
            "args": {"command": "pwd && ls"},
            "id": "tc-1",
        }
    )
    host._extract_query_from_args = MagicMock(return_value="pwd && ls")
    host._extract_tool_details = MagicMock(return_value="src/\ntests/")
    mixin = _mixin(host)
    mixin._emit_tool_result_stream = MagicMock()

    result_state = {
        "messages": [
            ToolMessage(content="src/\ntests/", tool_call_id="tc-1"),
        ]
    }

    mixin._emit_completed_status(result_state, [{"id": "tc-1"}])

    payload = host._event_sink.emit_tool_status.call_args[0][0]
    assert payload["tool_id"] == "tc-1"
    assert payload["tool_name"] == "execute_command"
    assert payload["query"] == "pwd && ls"
    assert payload["status"] == "completed"
    assert payload["details"] == "src/\ntests/"
    assert payload["conversation_id"] == 42
    host.logger.info.assert_called_once()
    # The streamed tool-status marker carries the output too.
    mixin._emit_tool_result_stream.assert_called_once_with(
        "tc-1", "execute_command", "pwd && ls", "src/\ntests/", "completed"
    )


def test_emit_completed_status_error_result_sets_error_status() -> None:
    """A tool result whose content signals failure emits status=error.

    The code-mode proxy flattens the harness's isError flag into the
    content text, so an ``Error:`` / ``[Error]`` prefix must turn the
    emitted status into ``error`` (the client then renders a red dot).
    """
    host = _MixinHost()
    host._extract_query_from_args = MagicMock(return_value="read a.py")
    host._extract_tool_details = MagicMock(
        return_value="Error: File does not exist: a.py"
    )
    mixin = _mixin(host)

    result_state = {
        "messages": [
            ToolMessage(
                content="Error: File does not exist: a.py",
                tool_call_id="tc-1",
            )
        ]
    }
    tool_calls = [
        {"id": "tc-1", "name": "read_file", "args": {"path": "a.py"}}
    ]

    with patch.object(mixin, "_emit_tool_result_stream") as stream_mock:
        mixin._emit_completed_status(result_state, tool_calls)

    payload = host._event_sink.emit_tool_status.call_args[0][0]
    assert payload["status"] == "error"
    assert payload["tool_name"] == "read_file"
    # The streamed marker carries the error status too.
    stream_mock.assert_called_once_with(
        "tc-1", "read_file", "read a.py", "Error: File does not exist: a.py",
        "error",
    )


def test_emit_completed_status_no_matching_call() -> None:
    """A ToolMessage with no matching tool call is skipped silently."""
    host = _MixinHost()
    host._find_matching_tool_call = MagicMock(return_value=None)
    mixin = _mixin(host)

    result_state = {
        "messages": [ToolMessage(content="orphaned", tool_call_id="zzz")]
    }

    mixin._emit_completed_status(result_state, [{"id": "tc-1"}])

    host._event_sink.emit_tool_status.assert_not_called()


def test_emit_completed_status_ignores_non_tool_messages() -> None:
    """Non-ToolMessage entries in state never emit a status."""
    host = _MixinHost()
    mixin = _mixin(host)

    result_state = {"messages": ["plain string", {"role": "user"}]}

    mixin._emit_completed_status(result_state, [])

    host._event_sink.emit_tool_status.assert_not_called()


# ---------------------------------------------------------------------------
# _maybe_restore_mood_state
# ---------------------------------------------------------------------------


def test_emit_tool_result_stream_sends_signal() -> None:
    """The tool result is pushed into the text stream as tool_status."""
    from airunner_services.llm.llm_response import LLMResponse

    host = _MixinHost()
    host._current_request_id = "req-9"
    host.send_llm_text_streamed_signal = MagicMock()
    mixin = _mixin(host)

    mixin._emit_tool_result_stream(
        "tc-1", "execute_command", "pwd && ls", "src/\nfile.ts"
    )

    host.send_llm_text_streamed_signal.assert_called_once()
    resp: LLMResponse = host.send_llm_text_streamed_signal.call_args[0][0]
    assert resp.message_type == "tool_status"
    assert resp.request_id == "req-9"
    import json as _json

    body = _json.loads(resp.message)
    assert body["tool_id"] == "tc-1"
    assert body["tool_name"] == "execute_command"
    assert body["status"] == "completed"
    assert body["details"] == "src/\nfile.ts"


def test_emit_tool_result_stream_no_sender_noop() -> None:
    """An owner without a stream-signal method is a silent no-op."""
    host = _MixinHost()  # no send_llm_text_streamed_signal attribute
    mixin = _mixin(host)
    mixin._emit_tool_result_stream("tc-1", "x", "q", "d")  # no raise


def test_emit_tool_result_stream_exception_swallowed() -> None:
    """A failing sender is logged, never propagated."""
    host = _MixinHost()
    host.send_llm_text_streamed_signal = MagicMock(
        side_effect=TypeError("bad signal")
    )
    mixin = _mixin(host)
    mixin._emit_tool_result_stream("tc-1", "x", "q", "d")  # no raise
    host.logger.warning.assert_called_once()


def test_mood_restore_applies_payload_and_reemits() -> None:
    """update_mood payload updates state, memory, and re-emits mood."""
    host = _MixinHost()
    payload = {
        "mood": "happy",
        "emoji": "😊",
        "kaomoji": "(＾▽＾)",
    }
    msg_hist = SimpleNamespace(_pending_bot_mood=None)
    host._memory = SimpleNamespace(message_history=msg_hist)
    host._current_mood = "neutral"
    host._current_emoji = "😐"
    host._current_kaomoji = "(｡◕ᴗ◕｡)"
    host._event_sink = MagicMock()
    mixin = _mixin(host)

    with patch(
        "airunner_services.llm.tools.mood_tools.get_last_mood_payload",
        return_value=payload,
    ):
        result_state: dict = {}
        mixin._maybe_restore_mood_state(result_state)

    assert result_state["current_mood"] == payload
    assert mixin._current_mood == "happy"
    assert mixin._current_emoji == "😊"
    assert mixin._current_kaomoji == "(＾▽＾)"
    assert msg_hist._pending_bot_mood == payload
    host._event_sink.emit_bot_mood.assert_called_once_with(payload)


def test_mood_restore_no_payload_keeps_state() -> None:
    """A None payload leaves state untouched and emits nothing."""
    host = _MixinHost()
    host._memory = SimpleNamespace(message_history=SimpleNamespace())
    mixin = _mixin(host)

    with patch(
        "airunner_services.llm.tools.mood_tools.get_last_mood_payload",
        return_value=None,
    ):
        result_state: dict = {"current_mood": "sentinel"}
        mixin._maybe_restore_mood_state(result_state)

    assert result_state["current_mood"] == "sentinel"
    host._event_sink.emit_bot_mood.assert_not_called()


def test_mood_restore_no_memory_and_no_event_sink() -> None:
    """Missing _memory and _event_sink attributes are tolerated."""
    host = _MixinHost()
    del host._event_sink
    mixin = _mixin(host)

    with patch(
        "airunner_services.llm.tools.mood_tools.get_last_mood_payload",
        return_value={"mood": "sleepy"},
    ):
        result_state: dict = {}
        mixin._maybe_restore_mood_state(result_state)

    assert result_state["current_mood"] == {"mood": "sleepy"}


def test_mood_restore_memory_without_message_history() -> None:
    """A _memory with no message_history skips the pending-mood write."""
    host = _MixinHost()
    host._memory = SimpleNamespace(message_history=None)
    mixin = _mixin(host)

    with patch(
        "airunner_services.llm.tools.mood_tools.get_last_mood_payload",
        return_value={"mood": "silly"},
    ):
        result_state: dict = {}
        mixin._maybe_restore_mood_state(result_state)

    assert result_state["current_mood"] == {"mood": "silly"}
    host._event_sink.emit_bot_mood.assert_called_once()


def test_mood_restore_exception_is_logged_not_raised() -> None:
    """A failing payload fetch logs and returns without raising."""
    host = _MixinHost()
    mixin = _mixin(host)

    with patch(
        "airunner_services.llm.tools.mood_tools.get_last_mood_payload",
        side_effect=RuntimeError("boom"),
    ):
        mixin._maybe_restore_mood_state({})

    host.logger.exception.assert_called_once()
