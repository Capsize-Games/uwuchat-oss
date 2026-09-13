"""Event sink and tool-action handler implementations for LLM workflows."""

from __future__ import annotations

import json
import logging
from typing import Any

from airunner_services.contract_enums import SignalCode

_logger = logging.getLogger("airunner_services.llm_workflow_sinks")


class MediatorSignalLLMWorkflowEventSink:
    """Adapter that forwards workflow events into the mediator signal path."""

    active = True

    def __init__(self, signal_emitter: Any) -> None:
        self._signal_emitter = signal_emitter

    def emit_tool_status(self, payload: dict[str, Any]) -> None:
        """Forward one tool-status payload through the mediator."""
        self._emit(SignalCode.LLM_TOOL_STATUS_SIGNAL, payload)
        self._emit_tool_status_stream(payload)

    def _emit_tool_status_stream(self, payload: dict[str, Any]) -> None:
        """Inject a tool-status marker into the LLM text stream."""
        try:
            from airunner_services.llm.llm_response import LLMResponse

            request_id = payload.get("request_id")
            response = LLMResponse(
                message=json.dumps(
                    {
                        "tool_id": payload.get("tool_id", ""),
                        "tool_name": payload.get("tool_name", ""),
                        "status": payload.get("status", ""),
                        "details": payload.get("details"),
                    }
                ),
                message_type="tool_status",
                is_end_of_message=False,
                request_id=request_id,
            )
            self._emit(
                SignalCode.LLM_TEXT_STREAMED_SIGNAL,
                {"response": response, "request_id": request_id},
            )
        except Exception:
            pass

    def emit_thinking(self, payload: dict[str, Any]) -> None:
        """Forward one thinking-status payload through the mediator."""
        self._emit(SignalCode.LLM_THINKING_SIGNAL, payload)

    def emit_bot_mood(self, payload: dict[str, Any]) -> None:
        """Forward one bot-mood payload through the mediator and text stream."""
        _logger.info(
            "emit_bot_mood: mood=%r kaomoji=%r request_id=%r",
            payload.get("mood"),
            payload.get("kaomoji"),
            payload.get("request_id"),
        )
        self._emit(SignalCode.BOT_MOOD_UPDATED, payload)
        self._emit_mood_stream(payload)

    def _emit_mood_stream(self, payload: dict[str, Any]) -> None:
        """Inject a mood marker into the LLM text stream."""
        try:
            from airunner_services.llm.llm_response import LLMResponse

            request_id = payload.get("request_id")
            response = LLMResponse(
                message=json.dumps(
                    {
                        "mood": payload.get("mood", "neutral"),
                        "emoji": payload.get("emoji", "😐"),
                        "kaomoji": payload.get(
                            "kaomoji", "(｡◕ᴗ◕｡)"
                        ),
                    }
                ),
                message_type="mood",
                is_end_of_message=False,
                request_id=request_id,
            )
            _logger.debug(
                "_emit_mood_stream: emitting LLM_TEXT_STREAMED_SIGNAL "
                "request_id=%r mood=%r",
                request_id,
                payload.get("mood"),
            )
            self._emit(
                SignalCode.LLM_TEXT_STREAMED_SIGNAL,
                {"response": response, "request_id": request_id},
            )
        except Exception:
            _logger.exception("_emit_mood_stream failed")

    def emit_stream_reset(
        self, request_id: "str | None"
    ) -> None:
        """Signal the client to clear its stream buffer and start fresh."""
        try:
            from airunner_services.llm.llm_response import LLMResponse

            response = LLMResponse(
                message="",
                message_type="stream_reset",
                is_end_of_message=False,
                request_id=request_id,
            )
            self._emit(
                SignalCode.LLM_TEXT_STREAMED_SIGNAL,
                {"response": response, "request_id": request_id},
            )
        except Exception:
            pass

    def _emit(self, code: SignalCode, payload: dict[str, Any]) -> None:
        """Emit one mediator payload when the emitter supports it."""
        emit_signal = getattr(self._signal_emitter, "emit_signal", None)
        if callable(emit_signal):
            emit_signal(code, payload)


_TOOL_ACTION_SIGNAL_CODES = {
    "agent_action_proposal": SignalCode.AGENT_ACTION_PROPOSAL_SIGNAL,
    "bot_mood_updated": SignalCode.BOT_MOOD_UPDATED,
    "clear_canvas": SignalCode.CANVAS_CLEAR_LINES_SIGNAL,
    "clear_conversation": SignalCode.LLM_CLEAR_HISTORY_SIGNAL,
    "conversation_deleted": SignalCode.CONVERSATION_DELETED,
    "conversation_title_updated": SignalCode.CONVERSATION_TITLE_UPDATED,
    "generate_image": SignalCode.SD_GENERATE_IMAGE_SIGNAL,
    "load_conversation": SignalCode.LOAD_CONVERSATION_SIGNAL,
    "load_image_from_path": SignalCode.CANVAS_LOAD_IMAGE_FROM_PATH_SIGNAL,
    "new_conversation": SignalCode.NEW_CONVERSATION_SIGNAL,
    "open_code_editor": SignalCode.OPEN_CODE_EDITOR,
    "quit_application": SignalCode.APPLICATION_QUIT_SIGNAL,
    "request_user_input": SignalCode.REQUEST_USER_INPUT_SIGNAL,
    "schedule_task": SignalCode.SCHEDULE_TASK_SIGNAL,
    "set_application_mode": SignalCode.SET_APPLICATION_MODE_SIGNAL,
    "toggle_tts": SignalCode.TOGGLE_TTS_SIGNAL,
}


class MediatorSignalLLMToolActionHandler:
    """Adapter that forwards tool actions into the mediator signal path."""

    active = True

    def __init__(self, signal_emitter: Any) -> None:
        self._signal_emitter = signal_emitter

    def handle_action(
        self,
        action: str,
        payload: dict[str, Any],
    ) -> bool:
        """Map one tool action to the compatibility signal path."""
        emit_signal = getattr(self._signal_emitter, "emit_signal", None)
        if not callable(emit_signal):
            return False
        signal_code, signal_payload = self._resolve_signal(action, payload)
        if signal_code is None:
            return False
        emit_signal(signal_code, signal_payload)
        return True

    def _resolve_signal(
        self,
        action: str,
        payload: dict[str, Any],
    ) -> tuple[SignalCode | None, dict[str, Any]]:
        """Resolve one tool action into a signal payload pair."""
        if action == "emit_signal":
            return self._legacy_signal(payload)
        return _TOOL_ACTION_SIGNAL_CODES.get(action), payload

    @staticmethod
    def _legacy_signal(
        payload: dict[str, Any],
    ) -> tuple[SignalCode | None, dict[str, Any]]:
        """Resolve one legacy signal action payload."""
        signal_name = str(payload.get("signal_name", "")).strip()
        if not signal_name:
            return None, payload
        try:
            signal_code = SignalCode[signal_name]
        except KeyError:
            return None, payload
        data = payload.get("data")
        if isinstance(data, dict):
            return signal_code, data
        return signal_code, {}
