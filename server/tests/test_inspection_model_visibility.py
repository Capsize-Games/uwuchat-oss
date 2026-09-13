"""Unit tests for inspection-model visibility and response grounding."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

from airunner_services.conf.model_settings import (
    CLAUDE_HAIKU_MODEL,
    GOOGLE_GEMINI_FLASH_MODEL,
)
from airunner_services.contract_enums import ModelService


# =========================================================================
# _iteration_label tests
# =========================================================================


class _FakeStreamingState:
    """Minimal stub for StreamingState with streamed_content."""

    def __init__(self, streamed_content: list[str] | None = None) -> None:
        self.streamed_content = streamed_content or []


def test_iteration_label_dialogue_tool_call() -> None:
    """DIALOGUE phase with tool_calls returns 'DIALOGUE (tool call)'."""
    from airunner_services.llm.managers.mixins.node_streaming_response_helper import (
        _iteration_label,
    )

    state = _FakeStreamingState(["some text"])
    result = _iteration_label(state, tool_calls=[{"name": "search"}],
                              phase="DIALOGUE")
    assert result == "DIALOGUE (tool call)"


def test_iteration_label_dialogue_response() -> None:
    """DIALOGUE phase with streamed content and no tools."""
    from airunner_services.llm.managers.mixins.node_streaming_response_helper import (
        _iteration_label,
    )

    state = _FakeStreamingState(["some text"])
    result = _iteration_label(state, tool_calls=None, phase="DIALOGUE")
    assert result == "DIALOGUE (response)"


def test_iteration_label_dialogue_empty() -> None:
    """DIALOGUE phase with no content and no tools."""
    from airunner_services.llm.managers.mixins.node_streaming_response_helper import (
        _iteration_label,
    )

    state = _FakeStreamingState([])
    result = _iteration_label(state, tool_calls=None, phase="DIALOGUE")
    assert result == "DIALOGUE"


def test_iteration_label_response_phase() -> None:
    """RESPONSE phase returns 'RESPONSE (response)' with content."""
    from airunner_services.llm.managers.mixins.node_streaming_response_helper import (
        _iteration_label,
    )

    state = _FakeStreamingState(["visible text"])
    result = _iteration_label(state, tool_calls=None, phase="RESPONSE")
    assert result == "RESPONSE (response)"


def test_iteration_label_response_empty() -> None:
    """RESPONSE phase with no content returns bare 'RESPONSE'."""
    from airunner_services.llm.managers.mixins.node_streaming_response_helper import (
        _iteration_label,
    )

    state = _FakeStreamingState([])
    result = _iteration_label(state, tool_calls=None, phase="RESPONSE")
    assert result == "RESPONSE"


def test_iteration_label_default_phase_is_dialogue() -> None:
    """When phase is omitted, default is DIALOGUE."""
    from airunner_services.llm.managers.mixins.node_streaming_response_helper import (
        _iteration_label,
    )

    state = _FakeStreamingState(["text"])
    result = _iteration_label(state, tool_calls=None)
    assert result == "DIALOGUE (response)"


# =========================================================================
# _capture_model_info tests
# =========================================================================


def _stub_model(
    model: str | None = None,
    model_name: str | None = None,
    provider: str | None = None,
) -> SimpleNamespace:
    """Build a stub chat-model object for _capture_model_info."""
    kwargs: dict = {}
    if model is not None:
        kwargs["model"] = model
    if model_name is not None:
        kwargs["model_name"] = model_name
    if provider is not None:
        kwargs["provider"] = provider
    return SimpleNamespace(**kwargs)


def test_capture_model_info_with_model_attribute() -> None:
    """Extract model_id from .model attribute."""
    from airunner_services.llm.managers.mixins.node_functions_mixin import (
        _capture_model_info,
    )

    stub = _stub_model(model=CLAUDE_HAIKU_MODEL)
    info = _capture_model_info(stub, "RESPONSE")
    assert info["model_id"] == CLAUDE_HAIKU_MODEL
    assert info["provider"] == "anthropic"
    assert info["pipeline_key"] == "RESPONSE"


def test_capture_model_info_falls_back_to_model_name() -> None:
    """Fall back to .model_name when .model is absent."""
    from airunner_services.llm.managers.mixins.node_functions_mixin import (
        _capture_model_info,
    )

    stub = _stub_model(model_name=GOOGLE_GEMINI_FLASH_MODEL)
    info = _capture_model_info(stub, "DIALOGUE")
    assert info["model_id"] == GOOGLE_GEMINI_FLASH_MODEL
    assert info["provider"] == ModelService.GOOGLE.value


def test_capture_model_info_explicit_provider() -> None:
    """Use explicit .provider when present, overriding prefix parse."""
    from airunner_services.llm.managers.mixins.node_functions_mixin import (
        _capture_model_info,
    )

    stub = _stub_model(model="openrouter/some-model",
                       provider=ModelService.OPENROUTER.value)
    info = _capture_model_info(stub, "DIALOGUE")
    assert info["provider"] == ModelService.OPENROUTER.value


def test_capture_model_info_no_provider_no_slash() -> None:
    """provider is empty string when model_id has no '/' and no .provider."""
    from airunner_services.llm.managers.mixins.node_functions_mixin import (
        _capture_model_info,
    )

    stub = _stub_model(model_name="simple-model")
    info = _capture_model_info(stub, "DIALOGUE")
    assert info["model_id"] == "simple-model"
    assert info["provider"] == ""


# =========================================================================
# _record_model_used_event tests
# =========================================================================


def _stub_owner(
    *,
    chatbot_id: int = 42,
    conversation_id: int = 100,
    session_id: int = 200,
    pipeline_key: str = "DIALOGUE",
    model_id: str = "test/model",
    provider: str = "test",
) -> MagicMock:
    """Build a mock owner with WorkflowManager, memory, and message history."""
    wm = MagicMock()
    wm.chatbot = SimpleNamespace(id=chatbot_id)
    wm._current_model_info = {
        "pipeline_key": pipeline_key,
        "model_id": model_id,
        "provider": provider,
    }

    conv = SimpleNamespace(id=conversation_id, session_id=session_id)
    msg_hist = MagicMock()
    msg_hist._conversation = conv
    memory = MagicMock()
    memory.message_history = msg_hist

    owner = MagicMock()
    owner._workflow_manager = wm
    owner._memory = memory
    return owner


def test_record_model_used_event_emits_correct_payload() -> None:
    """_record_model_used_event calls record() with correct payload."""
    from airunner_services.llm.managers.mixins.generation_execution_support import (
        _record_model_used_event,
    )

    owner = _stub_owner(
        chatbot_id=7,
        conversation_id=99,
        session_id=1,
        pipeline_key="RESPONSE",
        model_id=CLAUDE_HAIKU_MODEL,
        provider="anthropic",
    )

    with patch(
        "airunner_services.events.recorder.record",
    ) as mock_record:
        _record_model_used_event(owner)
        mock_record.assert_called_once_with(
            "model_used",
            chatbot_id=7,
            actor="assistant",
            payload={
                "pipeline_key": "RESPONSE",
                "model_id": CLAUDE_HAIKU_MODEL,
                "provider": "anthropic",
            },
            conversation_id=99,
            session_id=1,
        )


def test_record_model_used_event_respects_response_model_info() -> None:
    """When RESPONSE model ran, its info (not DIALOGUE) is recorded."""
    from airunner_services.llm.managers.mixins.generation_execution_support import (
        _record_model_used_event,
    )

    owner = _stub_owner(
        pipeline_key="RESPONSE",
        model_id=CLAUDE_HAIKU_MODEL,
        provider="anthropic",
    )

    with patch(
        "airunner_services.events.recorder.record",
    ) as mock_record:
        _record_model_used_event(owner)
        call_payload = mock_record.call_args[1]["payload"]
        assert call_payload["model_id"] == CLAUDE_HAIKU_MODEL
        assert call_payload["pipeline_key"] == "RESPONSE"


def test_record_model_used_event_dialogue_only() -> None:
    """When only DIALOGUE ran, its info is recorded."""
    from airunner_services.llm.managers.mixins.generation_execution_support import (
        _record_model_used_event,
    )

    owner = _stub_owner(
        pipeline_key="DIALOGUE",
        model_id=GOOGLE_GEMINI_FLASH_MODEL,
        provider=ModelService.GOOGLE.value,
    )

    with patch(
        "airunner_services.events.recorder.record",
    ) as mock_record:
        _record_model_used_event(owner)
        call_payload = mock_record.call_args[1]["payload"]
        assert call_payload["model_id"] == GOOGLE_GEMINI_FLASH_MODEL
        assert call_payload["pipeline_key"] == "DIALOGUE"


def test_record_model_used_event_no_workflow_manager() -> None:
    """Returns silently when _workflow_manager is missing."""
    from airunner_services.llm.managers.mixins.generation_execution_support import (
        _record_model_used_event,
    )

    owner = MagicMock()
    owner._workflow_manager = None

    with patch(
        "airunner_services.events.recorder.record",
    ) as mock_record:
        _record_model_used_event(owner)
        mock_record.assert_not_called()


def test_record_model_used_event_no_model_info() -> None:
    """Returns silently when _current_model_info is absent."""
    from airunner_services.llm.managers.mixins.generation_execution_support import (
        _record_model_used_event,
    )

    wm = MagicMock()
    wm._current_model_info = None
    owner = MagicMock()
    owner._workflow_manager = wm

    with patch(
        "airunner_services.events.recorder.record",
    ) as mock_record:
        _record_model_used_event(owner)
        mock_record.assert_not_called()
