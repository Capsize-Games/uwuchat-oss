"""Unit tests for llm_runtime route helpers.

Covers the runtime registry resolution, message conversion,
error-status mapping, the non-streaming invoke path, the streaming
``stream_runtime``/``next_stream_delta`` helpers, the websocket
envelope builder, and ``_resolve_model_for_storage``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from airunner_services.api.routes import llm_runtime as mod
from airunner_services.ipc.messages import (
    EnvelopeStatus,
    RequestEnvelope,
    ResponseEnvelope,
    StreamDelta,
)
from airunner_services.runtimes.contracts import (
    MessageRole,
    RuntimeAction,
    RuntimeKind,
)


class _FakeClient:
    """Minimal RuntimeClient with an invoke stub."""

    def __init__(self, result=None, error=None) -> None:
        self._result = result
        self._error = error

    def invoke(self, envelope):
        if self._error is not None:
            return self._error
        return self._result or ResponseEnvelope(
            request_id="req-1",
            status=EnvelopeStatus.SUCCEEDED,
            payload={"content": "hi"},
            metadata={"prompt_tokens": 5, "completion_tokens": 3},
        )

    def stream(self, envelope):
        yield StreamDelta(request_id="req-1", final=False, delta={"content": "a"})
        yield StreamDelta(request_id="req-1", final=True, delta={"content": "b"})


# ---------------------------------------------------------------------------
# get_runtime_registry / require_runtime_registry / require_websocket...
# ---------------------------------------------------------------------------


def test_get_runtime_registry_returns_state() -> None:
    registry = MagicMock()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        runtime_registry=registry,
    )))
    assert mod.get_runtime_registry(request) is registry


def test_get_runtime_registry_missing_returns_none() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    assert mod.get_runtime_registry(request) is None


def test_require_runtime_registry_returns() -> None:
    registry = MagicMock()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        runtime_registry=registry,
    )))
    assert mod.require_runtime_registry(request) is registry


def test_require_runtime_registry_raises() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(Exception) as exc:
        mod.require_runtime_registry(request)
    assert exc.value.status_code == 503


def test_require_websocket_runtime_registry_returns() -> None:
    registry = MagicMock()
    ws = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        runtime_registry=registry,
    )))
    assert mod.require_websocket_runtime_registry(ws) is registry


def test_require_websocket_runtime_registry_raises() -> None:
    ws = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(Exception) as exc:
        mod.require_websocket_runtime_registry(ws)
    assert exc.value.status_code == 503


# ---------------------------------------------------------------------------
# resolve_llm_client
# ---------------------------------------------------------------------------


def test_resolve_llm_client_returns_resolved() -> None:
    client = MagicMock()
    registry = MagicMock()
    registry.resolve.return_value = client
    assert mod.resolve_llm_client(registry) is client
    registry.resolve.assert_called_once()


def test_resolve_llm_client_missing_raises_503() -> None:
    registry = MagicMock()
    registry.resolve.side_effect = KeyError("llm")
    with pytest.raises(Exception) as exc:
        mod.resolve_llm_client(registry)
    assert exc.value.status_code == 503


# ---------------------------------------------------------------------------
# to_runtime_messages / _parse_messages
# ---------------------------------------------------------------------------


def test_to_runtime_messages_valid() -> None:
    msgs = [
        SimpleNamespace(role="user", content="hi"),
        SimpleNamespace(role="assistant", content="hello"),
    ]
    out = mod.to_runtime_messages(msgs)
    assert out[0].role == MessageRole.USER
    assert out[0].content == "hi"
    assert out[1].role == MessageRole.ASSISTANT


def test_to_runtime_messages_bad_role_raises_400() -> None:
    with pytest.raises(Exception) as exc:
        mod.to_runtime_messages([SimpleNamespace(role="nope", content="x")])
    assert exc.value.status_code == 400


def test_parse_messages_filters_empty_content() -> None:
    out = mod._parse_messages(
        [
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "   "},
            {"role": "unknown", "content": "x"},
        ]
    )
    assert len(out) == 2
    assert out[0].role == MessageRole.USER
    # Unknown role falls back to USER per _ROLE_MAP default.
    assert out[1].role == MessageRole.USER


# ---------------------------------------------------------------------------
# runtime_error_status / raise_for_runtime_error
# ---------------------------------------------------------------------------


def test_runtime_error_status_timeout() -> None:
    resp = SimpleNamespace(
        error=SimpleNamespace(code="llm_timeout", message="slow")
    )
    assert mod.runtime_error_status(resp) == 504


def test_runtime_error_status_other() -> None:
    resp = SimpleNamespace(error=SimpleNamespace(code="boom", message="x"))
    assert mod.runtime_error_status(resp) == 502


def test_raise_for_runtime_error_success() -> None:
    resp = SimpleNamespace(status=EnvelopeStatus.SUCCEEDED, error=None)
    mod.raise_for_runtime_error(resp)  # no raise


def test_raise_for_runtime_error_failed_with_message() -> None:
    resp = SimpleNamespace(
        status=EnvelopeStatus.FAILED,
        error=SimpleNamespace(message="it broke", code="x"),
    )
    with pytest.raises(Exception) as exc:
        mod.raise_for_runtime_error(resp)
    assert exc.value.detail == "it broke"
    assert exc.value.status_code == 502


def test_raise_for_runtime_error_failed_no_message() -> None:
    resp = SimpleNamespace(status=EnvelopeStatus.FAILED, error=None)
    with pytest.raises(Exception) as exc:
        mod.raise_for_runtime_error(resp)
    assert exc.value.detail == "LLM runtime request failed"


# ---------------------------------------------------------------------------
# invoke_llm_runtime
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_llm_runtime_success() -> None:
    result = await mod.invoke_llm_runtime(
        _FakeClient(), [], "m", None, 0.7, 500,
    )
    assert result.content == "hi"
    assert result.prompt_tokens == 5
    assert result.completion_tokens == 3
    assert result.total_tokens == 0


@pytest.mark.asyncio
async def test_invoke_llm_runtime_stateless_metadata() -> None:
    client = _FakeClient()
    with patch.object(client, "invoke") as invoke:
        invoke.return_value = ResponseEnvelope(
            request_id="r", status=EnvelopeStatus.SUCCEEDED,
            payload={"content": "c"},
            metadata={},
        )
        result = await mod.invoke_llm_runtime(
            client, [], "m", "cpu", 0.9, 100, stateless=True,
        )
    envelope = invoke.call_args[0][0]
    payload = envelope.payload
    assert payload["metadata"]["stateless"] is True
    assert payload["metadata"]["gguf_runtime_profile"] == "cpu"
    assert result.content == "c"


@pytest.mark.asyncio
async def test_invoke_llm_runtime_failure_raises() -> None:
    from airunner_services.ipc.messages import ErrorEnvelope

    client = _FakeClient(
        error=ResponseEnvelope(
            request_id="r", status=EnvelopeStatus.FAILED,
            error=ErrorEnvelope(code="x", message="boom"),
        )
    )
    with pytest.raises(Exception) as exc:
        await mod.invoke_llm_runtime(client, [], "m", None, 0.7, 500)
    assert exc.value.detail == "boom"


# ---------------------------------------------------------------------------
# run_runtime_action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_runtime_action_success() -> None:
    client = _FakeClient()
    await mod.run_runtime_action(client, RuntimeAction.LOAD_MODEL)  # no raise


@pytest.mark.asyncio
async def test_run_runtime_action_failure_raises() -> None:
    from airunner_services.ipc.messages import ErrorEnvelope

    client = _FakeClient(
        error=ResponseEnvelope(
            request_id="r", status=EnvelopeStatus.FAILED,
            error=ErrorEnvelope(code="x", message="no"),
        )
    )
    with pytest.raises(Exception):
        await mod.run_runtime_action(client, RuntimeAction.LOAD_MODEL)


# ---------------------------------------------------------------------------
# stream_runtime / next_stream_delta
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_next_stream_delta_returns_item() -> None:
    delta = StreamDelta(request_id="r", final=False)
    assert await mod.next_stream_delta(iter([delta])) is delta


@pytest.mark.asyncio
async def test_next_stream_delta_exhausted_raises() -> None:
    # An exhausted iterator yields the sentinel → StopAsyncIteration
    # (the async-stream termination signal stream_runtime catches).
    with pytest.raises(StopAsyncIteration):
        await mod.next_stream_delta(iter([]))


@pytest.mark.asyncio
async def test_stream_runtime_yields_all() -> None:
    deltas = [d async for d in mod.stream_runtime(_FakeClient(), object())]
    assert [d.delta["content"] for d in deltas] == ["a", "b"]


# ---------------------------------------------------------------------------
# websocket_envelope
# ---------------------------------------------------------------------------


def test_websocket_envelope_defaults() -> None:
    env = mod.websocket_envelope({"message": "hi"})
    assert env.runtime == RuntimeKind.LLM
    assert env.action == RuntimeAction.INVOKE
    assert env.stream is True
    payload = env.payload
    assert payload["stream"] is True
    assert payload["messages"][0]["content"] == "hi"


def test_websocket_envelope_max_tokens_clamped() -> None:
    env = mod.websocket_envelope(
        {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 900},
        max_tokens_ceiling=500,
    )
    assert env.payload["max_tokens"] == 500


def test_websocket_envelope_max_tokens_defaults_to_ceiling() -> None:
    env = mod.websocket_envelope(
        {"messages": [{"role": "user", "content": "hi"}]},
        max_tokens_ceiling=300,
    )
    assert env.payload["max_tokens"] == 300


def test_websocket_envelope_no_ceiling_keeps_raw() -> None:
    env = mod.websocket_envelope(
        {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 123}
    )
    assert env.payload["max_tokens"] == 123


def test_websocket_envelope_active_documents() -> None:
    env = mod.websocket_envelope(
        {
            "messages": [{"role": "user", "content": "hi"}],
            "active_document_ids": [1, 2],
        }
    )
    assert env.payload["metadata"]["active_document_ids"] == [1, 2]


def test_websocket_envelope_persists_rag() -> None:
    with patch.object(mod, "_persist_rag_to_conversation") as persist:
        mod.websocket_envelope(
            {
                "messages": [{"role": "user", "content": "hi"}],
                "conversation_id": 5,
            }
        )
    persist.assert_called_once()


# ---------------------------------------------------------------------------
# _resolve_model_for_storage
# ---------------------------------------------------------------------------


def test_resolve_model_for_storage_none() -> None:
    assert mod._resolve_model_for_storage(None) is None


def test_resolve_model_for_storage_no_router() -> None:
    with patch(
        "airunner_services.llm.model_router.load_project_router",
        return_value=None,
    ):
        assert mod._resolve_model_for_storage("m") == "m"


def test_resolve_model_for_storage_router_rule() -> None:
    router = MagicMock()
    router.rule.return_value = {"model": "routed-model"}
    with patch(
        "airunner_services.llm.model_router.load_project_router",
        return_value=router,
    ):
        assert mod._resolve_model_for_storage("m") == "routed-model"


def test_resolve_model_for_storage_router_no_rule() -> None:
    router = MagicMock()
    router.rule.return_value = None
    with patch(
        "airunner_services.llm.model_router.load_project_router",
        return_value=router,
    ):
        assert mod._resolve_model_for_storage("m") == "m"


def test_resolve_model_for_storage_exception() -> None:
    with patch(
        "airunner_services.llm.model_router.load_project_router",
        side_effect=RuntimeError("boom"),
    ):
        assert mod._resolve_model_for_storage("m") == "m"


# ---------------------------------------------------------------------------
# _conversation_is_code_mode remaining branches
# ---------------------------------------------------------------------------


def test_code_mode_no_project_setting_uses_settings() -> None:
    """When AIRUNNER_PROJECT is unset, the settings fallback is used."""
    import sys
    from types import ModuleType

    stub = ModuleType("projects.uwuchat.server.code_mode_service")
    stub.get_code_mode = lambda conv_id: True
    with patch.dict("os.environ", {}, clear=True), patch(
        "airunner_services.conf.settings"
    ) as settings, patch.dict(
        sys.modules, {"projects.uwuchat.server.code_mode_service": stub}
    ):
        settings.AIRUNNER_PROJECT = "uwuchat"
        assert mod._conversation_is_code_mode(7) is True


def test_code_mode_empty_project_returns_false() -> None:
    """An empty resolved project string returns False."""
    with patch.dict("os.environ", {}, clear=True), patch(
        "airunner_services.conf.settings"
    ) as settings:
        settings.AIRUNNER_PROJECT = ""
        assert mod._conversation_is_code_mode(7) is False


def test_code_mode_module_without_func_returns_false() -> None:
    """A project module without get_code_mode returns False."""
    import sys
    from types import ModuleType

    stub = ModuleType("projects.uwuchat.server.code_mode_service")  # no func
    with patch.dict("os.environ", {"AIRUNNER_PROJECT": "uwuchat"}), patch.dict(
        sys.modules, {"projects.uwuchat.server.code_mode_service": stub}
    ):
        assert mod._conversation_is_code_mode(7) is False
