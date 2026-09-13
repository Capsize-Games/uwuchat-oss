"""Unit tests for the LocalFallbackLLMClient static helpers.

Covers ``response_message``, ``is_complete``, ``response_metadata``
(including message_type/call_chain_id passthrough), ``resolve_action``,
``timeout_response``, and ``failure_delta``.
"""

from __future__ import annotations

from types import SimpleNamespace

from airunner_services.ipc.messages import EnvelopeStatus

from airunner_services.runtimes.local_fallback._llm_client_helpers import (
    failure_delta,
    is_complete,
    resolve_action,
    response_message,
    response_metadata,
    timeout_response,
)


def _resp(**kwargs) -> SimpleNamespace:
    defaults = {
        "message": "",
        "is_system_message": False,
        "is_end_of_message": False,
        "final_visible_message": None,
        "message_type": None,
        "call_chain_id": None,
        "tools": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_response_message() -> None:
    assert response_message(_resp(message="hi")) == "hi"
    assert response_message(_resp()) == ""


def test_is_complete() -> None:
    assert is_complete(_resp(is_end_of_message=True)) is True
    assert is_complete(_resp(is_end_of_message=False)) is False


def test_response_metadata_empty() -> None:
    assert response_metadata(_resp()) == {}


def test_response_metadata_usage_fields() -> None:
    meta = response_metadata(
        _resp(
            tools=["a"],
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
    )
    assert meta["tools"] == ["a"]
    assert meta["prompt_tokens"] == 10
    assert meta["completion_tokens"] == 5
    assert meta["total_tokens"] == 15


def test_response_metadata_message_type() -> None:
    meta = response_metadata(_resp(message_type="tool_status"))
    assert meta["message_type"] == "tool_status"


def test_response_metadata_call_chain_id() -> None:
    meta = response_metadata(_resp(call_chain_id="chain-1"))
    assert meta["call_chain_id"] == "chain-1"


def test_resolve_action_returns_chat() -> None:
    action = resolve_action()
    # LLMActionType.CHAT — its value is the framework's chat action label.
    assert action is not None
    assert "respond" in str(getattr(action, "value", ""))


def test_timeout_response_shape() -> None:
    resp = timeout_response("req-1", "slow")
    assert resp.request_id == "req-1"
    assert resp.status is EnvelopeStatus.FAILED
    assert resp.error.code == "llm_timeout"
    assert resp.error.message == "slow"
    assert resp.error.retryable is True


def test_failure_delta_shape() -> None:
    delta = failure_delta("req-1", "boom")
    assert delta.request_id == "req-1"
    assert delta.final is True
    assert delta.status is EnvelopeStatus.FAILED
    assert delta.metadata["error"] == "boom"
