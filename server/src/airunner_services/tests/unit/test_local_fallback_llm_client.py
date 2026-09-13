"""Unit tests for LocalFallbackLLMClient streaming surface.

Covers ``_stream_responses`` (system-message deltas, terminal-content
fallback, timeout), ``_terminal_content``, the ``stream()``/``cancel()``
public surface, and the prompt-extraction helpers.  Focuses on the
drop-path: deltas yielded here are what the websocket payload builder
turns into GUI-visible events.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from airunner_services.ipc.messages import StreamDelta
from airunner_services.runtimes.contracts import RuntimeAction, RuntimeKind


class _FakeResponse:
    """Minimal response object matching what _stream_responses reads."""

    def __init__(
        self,
        message: str = "",
        is_system_message: bool = False,
        is_end_of_message: bool = False,
        final_visible_message: str | None = None,
        message_type: str | None = None,
    ) -> None:
        self.message = message
        self.is_system_message = is_system_message
        self.is_end_of_message = is_end_of_message
        self.final_visible_message = final_visible_message
        self.message_type = message_type


def _client(**attrs) -> MagicMock:
    """Build a LocalFallbackLLMClient without running __init__."""
    from airunner_services.runtimes.local_fallback._llm_client import (
        LocalFallbackLLMClient,
    )

    client = LocalFallbackLLMClient.__new__(LocalFallbackLLMClient)
    defaults = {
        "_timeout_seconds": 5,
        "_mediator": MagicMock(),
        "_llm_service": MagicMock(),
        "_llm_request_factory": MagicMock(return_value=MagicMock()),
    }
    defaults.update(attrs)
    for k, v in defaults.items():
        setattr(client, k, v)
    return client


# ---------------------------------------------------------------------------
# _terminal_content
# ---------------------------------------------------------------------------


def test_terminal_content_returns_message() -> None:
    from airunner_services.runtimes.local_fallback._llm_client import (
        _terminal_content,
    )

    resp = _FakeResponse(message="hello", is_end_of_message=True)
    assert _terminal_content(resp, True, True) == "hello"


def test_terminal_content_falls_back_to_final_visible() -> None:
    from airunner_services.runtimes.local_fallback._llm_client import (
        _terminal_content,
    )

    resp = _FakeResponse(
        message="", is_end_of_message=True, final_visible_message="full"
    )
    assert _terminal_content(resp, True, False) == "full"


def test_terminal_content_empty_when_yielded() -> None:
    from airunner_services.runtimes.local_fallback._llm_client import (
        _terminal_content,
    )

    resp = _FakeResponse(message="", is_end_of_message=True)
    assert _terminal_content(resp, True, True) == ""


# ---------------------------------------------------------------------------
# _stream_responses
# ---------------------------------------------------------------------------


def test_stream_responses_yields_normal_deltas() -> None:
    client = _client()
    responses = iter(
        [
            _FakeResponse(message="Hello"),
            _FakeResponse(message=" world", is_end_of_message=True),
        ]
    )
    with patch.object(client, "_iter_responses", return_value=responses):
        deltas = list(client._stream_responses("req-1", None))

    assert len(deltas) == 2
    assert deltas[0].delta["content"] == "Hello"
    assert deltas[0].final is False
    assert deltas[1].delta["content"] == " world"
    assert deltas[1].final is True


def test_stream_responses_system_message_then_normal() -> None:
    client = _client()
    responses = iter(
        [
            _FakeResponse(
                message="Error: boom", is_system_message=True,
                is_end_of_message=False,
            ),
            _FakeResponse(message="", is_end_of_message=True),
        ]
    )
    with patch.object(client, "_iter_responses", return_value=responses):
        deltas = list(client._stream_responses("req-1", None))

    assert deltas[0].metadata["message_type"] == "system"
    assert deltas[0].final is False
    assert deltas[1].final is True


def test_stream_responses_terminal_system_message_returns() -> None:
    client = _client()
    responses = iter(
        [
            _FakeResponse(
                message="Fatal", is_system_message=True,
                is_end_of_message=True,
            ),
        ]
    )
    with patch.object(client, "_iter_responses", return_value=responses):
        deltas = list(client._stream_responses("req-1", None))

    assert len(deltas) == 1
    assert deltas[0].metadata["message_type"] == "system"
    assert deltas[0].final is True


def test_stream_responses_timeout_raises() -> None:
    client = _client()
    with patch.object(client, "_iter_responses", side_effect=TimeoutError("t")):
        try:
            list(client._stream_responses("req-1", None))
        except TimeoutError:
            pass
        else:
            raise AssertionError("expected TimeoutError")


def test_stream_responses_yields_metadata() -> None:
    """message_type flows into delta metadata via response_metadata."""
    client = _client()
    responses = iter(
        [
            _FakeResponse(
                message="chunk", message_type="tool_status",
                is_end_of_message=True,
            ),
        ]
    )
    with patch.object(client, "_iter_responses", return_value=responses):
        deltas = list(client._stream_responses("req-1", None))

    assert deltas[0].metadata.get("message_type") == "tool_status"


# ---------------------------------------------------------------------------
# stream() wrapper
# ---------------------------------------------------------------------------


def test_stream_wrapper_yields_and_unregisters() -> None:
    client = _client()
    client._validate_request = MagicMock(return_value=MagicMock(metadata={}))
    client._dispatch = MagicMock(return_value=MagicMock())
    client._stream_responses = MagicMock(
        return_value=iter([StreamDelta(request_id="req-1")])
    )

    envelope = MagicMock(
        runtime=RuntimeKind.LLM, action=RuntimeAction.INVOKE,
        request_id="req-1",
    )
    deltas = list(client.stream(envelope))

    assert len(deltas) == 1
    client._mediator.unregister_pending_request.assert_called_once_with(
        "req-1"
    )


def test_stream_wrapper_timeout_yields_failure_delta() -> None:
    client = _client()
    client._validate_request = MagicMock(return_value=MagicMock(metadata={}))
    client._dispatch = MagicMock(return_value=MagicMock())
    client._stream_responses = MagicMock(side_effect=TimeoutError("slow"))

    envelope = MagicMock(
        runtime=RuntimeKind.LLM, action=RuntimeAction.INVOKE,
        request_id="req-1",
    )
    deltas = list(client.stream(envelope))

    assert len(deltas) == 1
    assert deltas[0].status is not None


def test_stream_responses_timeout_when_no_terminal() -> None:
    """Exhausting the iterator without a terminal response raises.

    Covers the trailing ``raise TimeoutError`` in ``_stream_responses``
    after the for loop completes with no is_end_of_message=True.
    """
    client = _client()
    responses = iter(
        [
            _FakeResponse(message="mid"),
            _FakeResponse(message="more"),
        ]
    )
    with patch.object(client, "_iter_responses", return_value=responses):
        try:
            list(client._stream_responses("req-1", None))
        except TimeoutError:
            pass
        else:
            raise AssertionError("expected TimeoutError")


def test_cancel_interrupts_and_returns_cancelled() -> None:
    client = _client()
    client._llm_service.interrupt = MagicMock()
    resp = client.cancel("req-1")
    client._llm_service.interrupt.assert_called_once()
    assert resp.status.value.lower() == "cancelled"


def test_cancel_without_interrupt() -> None:
    client = _client()
    del client._llm_service.interrupt
    resp = client.cancel("req-1")
    assert resp.status.value.lower() == "cancelled"


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


def test_prompt_from_messages_last_user_message() -> None:
    from airunner_services.runtimes.contracts import MessageRole

    client = _client()
    user1 = MagicMock(role=MessageRole.USER, content="first")
    user2 = MagicMock(role=MessageRole.USER, content="second")
    invocation = MagicMock(messages=[user1, user2])
    assert client._prompt_from_messages(invocation) == "second"


def test_prompt_from_messages_empty_logs_error() -> None:
    client = _client()
    invocation = MagicMock(messages=[])
    assert client._prompt_from_messages(invocation) == ""


def test_system_prompt_found() -> None:
    from airunner_services.runtimes.contracts import MessageRole

    client = _client()
    sys = MagicMock(role=MessageRole.SYSTEM, content="be nice")
    invocation = MagicMock(messages=[sys])
    assert client._system_prompt(invocation) == "be nice"


def test_system_prompt_missing() -> None:
    from airunner_services.runtimes.contracts import MessageRole

    client = _client()
    user = MagicMock(role=MessageRole.USER, content="hi")
    invocation = MagicMock(messages=[user])
    assert client._system_prompt(invocation) is None


# ---------------------------------------------------------------------------
# invoke() surface (status/load/unload/error paths)
# ---------------------------------------------------------------------------


def test_invoke_non_llm_runtime_raises() -> None:
    client = _client()
    envelope = MagicMock(runtime=RuntimeKind.ART)
    try:
        client.invoke(envelope)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_invoke_status_action() -> None:
    client = _client()
    client._status_response = MagicMock(return_value="status-ok")
    envelope = MagicMock(
        runtime=RuntimeKind.LLM, action=RuntimeAction.STATUS,
        request_id="req-1",
    )
    assert client.invoke(envelope) == "status-ok"


def test_invoke_load_model_action() -> None:
    client = _client()
    client._load_model = MagicMock(return_value="loaded")
    envelope = MagicMock(
        runtime=RuntimeKind.LLM, action=RuntimeAction.LOAD_MODEL,
        request_id="req-1",
    )
    assert client.invoke(envelope) == "loaded"


def test_invoke_unload_model_action() -> None:
    client = _client()
    client._unload_model = MagicMock(return_value="unloaded")
    envelope = MagicMock(
        runtime=RuntimeKind.LLM, action=RuntimeAction.UNLOAD_MODEL,
        request_id="req-1",
    )
    assert client.invoke(envelope) == "unloaded"


def test_invoke_dispatch_collect_and_timeout() -> None:
    client = _client()
    client._validate_request = MagicMock(return_value=MagicMock(metadata={}))
    client._dispatch = MagicMock(return_value=MagicMock())
    client._collect_response = MagicMock(side_effect=TimeoutError("slow"))

    envelope = MagicMock(
        runtime=RuntimeKind.LLM, action=RuntimeAction.INVOKE,
        request_id="req-1",
    )
    resp = client.invoke(envelope)
    assert resp.status.value.lower() == "failed"


def test_validate_request_rejects_non_invoke() -> None:
    client = _client()
    envelope = MagicMock(
        runtime=RuntimeKind.LLM, action=RuntimeAction.STATUS
    )
    try:
        client._validate_request(envelope)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


# ---------------------------------------------------------------------------
# _prepare_llm_request option passthrough
# ---------------------------------------------------------------------------


def test_prepare_llm_request_sets_options() -> None:
    client = _client()
    invocation = MagicMock(
        messages=[],
        tool_choice="force_tool_x",
        metadata={
            "active_document_ids": [1, 2],
            "gguf_runtime_profile": "  cpu  ",
            "stateless": True,
        },
    )
    request = MagicMock()
    client._llm_request_factory.return_value = request
    client._system_prompt = MagicMock(return_value="sys")

    client._prepare_llm_request(invocation)

    assert request.system_prompt == "sys"
    assert request.force_tool == "force_tool_x"
    assert request.active_document_ids == [1, 2]
    assert request.gguf_runtime_profile == "cpu"
    assert request.stateless is True


def test_prepare_llm_request_skips_empty_options() -> None:
    client = _client()
    invocation = MagicMock(
        messages=[],
        tool_choice="auto",
        metadata={},
    )
    request = SimpleNamespace()
    client._llm_request_factory.return_value = request
    client._system_prompt = MagicMock(return_value=None)

    client._prepare_llm_request(invocation)

    assert not hasattr(request, "system_prompt")
    assert not hasattr(request, "force_tool")
    assert not hasattr(request, "active_document_ids")
    assert not hasattr(request, "gguf_runtime_profile")
    assert not hasattr(request, "stateless")


# ---------------------------------------------------------------------------
# __init__ / _dispatch / _collect_response / _iter_responses
# ---------------------------------------------------------------------------


def test_init_sets_defaults() -> None:
    """Constructing with mocks wires service, factory, and base attrs."""
    from airunner_services.runtimes.local_fallback._llm_client import (
        LocalFallbackLLMClient,
    )

    service = MagicMock()
    mediator = MagicMock()
    factory = MagicMock(return_value=SimpleNamespace())
    client = LocalFallbackLLMClient(
        llm_service=service,
        mediator=mediator,
        llm_request_factory=factory,
    )
    assert client._llm_service is service
    assert client._mediator is mediator
    assert client._llm_request_factory is factory
    assert client.descriptor is not None


def test_init_builds_default_service() -> None:
    """No service passed → _build_llm_service() is used."""
    from airunner_services.runtimes.local_fallback._llm_client import (
        LocalFallbackLLMClient,
    )

    with patch(
        "airunner_services.runtimes.local_fallback._llm_client._build_llm_service",
        return_value=SimpleNamespace(),
    ), patch(
        "airunner_services.runtimes.local_fallback._llm_client._build_llm_request",
        return_value=SimpleNamespace(),
    ):
        client = LocalFallbackLLMClient(mediator=MagicMock())
    assert client._llm_service is not None


def test_validate_request_accepts_invoke() -> None:
    """A valid INVOKE envelope validates into LLMInvocationRequest."""
    client = _client()
    from airunner_services.ipc.messages import RequestEnvelope
    from airunner_services.runtimes.contracts import (
        RuntimeAction,
        RuntimeKind,
    )

    envelope = RequestEnvelope(
        request_id="req-1",
        runtime=RuntimeKind.LLM,
        action=RuntimeAction.INVOKE,
        payload={"model": "m", "messages": [], "metadata": {}},
    )
    invocation = client._validate_request(envelope)
    assert invocation.model == "m"


def test_load_model_delegates() -> None:
    """_load_model forwards to the base wait-for-status helper."""
    client = _client()
    client._wait_for_model_status = MagicMock(return_value="loaded")
    assert client._load_model("req-1") == "loaded"
    client._wait_for_model_status.assert_called_once()


def test_unload_model_delegates() -> None:
    """_unload_model forwards to the base wait-for-status helper."""
    client = _client()
    client._wait_for_model_status = MagicMock(return_value="unloaded")
    assert client._unload_model("req-1") == "unloaded"
    client._wait_for_model_status.assert_called_once()


def test_dispatch_sends_request_and_returns_queue() -> None:
    """_dispatch registers a pending request and sends via the service."""
    client = _client()
    queue = MagicMock()
    client._mediator.register_pending_request = MagicMock(return_value=queue)
    client._llm_service.send_request = MagicMock()
    client._prompt_from_messages = MagicMock(return_value="prompt")
    client._prepare_llm_request = MagicMock(return_value="req")

    invocation = MagicMock(metadata={"conversation_id": 5, "chatbot_id": 3})

    result = client._dispatch(MagicMock(request_id="req-1"), invocation)

    assert result is queue
    client._mediator.register_pending_request.assert_called_once_with("req-1")
    client._llm_service.send_request.assert_called_once()


def test_dispatch_exception_unregisters_and_raises() -> None:
    """A send failure unregisters the pending request and re-raises."""
    client = _client()
    client._mediator.register_pending_request = MagicMock(
        return_value=MagicMock()
    )
    client._llm_service.send_request = MagicMock(
        side_effect=RuntimeError("boom")
    )
    client._prompt_from_messages = MagicMock(return_value="")
    client._prepare_llm_request = MagicMock(return_value=MagicMock())

    try:
        client._dispatch(MagicMock(request_id="req-1"), MagicMock(metadata={}))
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")
    client._mediator.unregister_pending_request.assert_called_once_with("req-1")


def test_collect_response_joins_chunks() -> None:
    """_collect_response concatenates messages and returns the envelope."""
    client = _client()
    client._iter_responses = MagicMock(
        return_value=iter(
            [
                _FakeResponse(message="Hel"),
                _FakeResponse(message="lo", is_end_of_message=True),
            ]
        )
    )
    resp = client._collect_response("req-1", MagicMock())
    assert resp.payload["content"] == "Hello"
    assert resp.status.value == "succeeded"


def test_collect_response_timeout() -> None:
    """_collect_response raises TimeoutError when nothing completes."""
    client = _client()
    client._iter_responses = MagicMock(return_value=iter([]))
    try:
        client._collect_response("req-1", MagicMock())
    except TimeoutError:
        pass
    else:
        raise AssertionError("expected TimeoutError")


def test_iter_responses_yields_and_skips_no_response() -> None:
    """_iter_responses pulls {'response': ...} dicts off the queue.

    Items whose 'response' value is None are skipped; once the queue
    drains, get() raises Empty → TimeoutError, which terminates the
    generator when no terminal response arrives.
    """
    client = _client()
    from queue import Queue

    q: Queue = Queue()
    q.put({"response": "one"})
    q.put({"response": None})  # skipped

    client._timeout_seconds = 0.01
    yielded: list = []
    gen = client._iter_responses(q)
    try:
        while True:
            yielded.append(next(gen))
    except TimeoutError:
        pass
    assert yielded == ["one"]


def test_iter_responses_timeout_on_empty() -> None:
    """An empty queue raises TimeoutError after the timeout."""
    client = _client()
    from queue import Queue

    q: Queue = Queue()
    client._timeout_seconds = 0.01
    try:
        list(client._iter_responses(q))
    except TimeoutError:
        pass
    else:
        raise AssertionError("expected TimeoutError")
