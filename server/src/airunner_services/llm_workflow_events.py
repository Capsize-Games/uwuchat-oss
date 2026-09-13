"""Service-side event sinks for LLM workflow orchestration."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMWorkflowEventSink(Protocol):
    """Protocol for workflow progress and tool-status event sinks."""

    active: bool

    def emit_tool_status(self, payload: dict[str, Any]) -> None:
        """Publish one tool-status payload."""

    def emit_thinking(self, payload: dict[str, Any]) -> None:
        """Publish one thinking-status payload."""

    def emit_bot_mood(self, payload: dict[str, Any]) -> None:
        """Publish one bot-mood payload."""

    def emit_stream_reset(self, request_id: "str | None") -> None:
        """Signal the client to clear its stream buffer and retry."""


@runtime_checkable
class LLMToolActionHandler(Protocol):
    """Protocol for service-owned tool side effects."""

    active: bool

    def handle_action(
        self,
        action: str,
        payload: dict[str, Any],
    ) -> bool:
        """Handle one tool action payload."""


class NullLLMWorkflowEventSink:
    """No-op sink used for service-only workflow execution."""

    active = False

    def emit_tool_status(self, payload: dict[str, Any]) -> None:
        del payload

    def emit_thinking(self, payload: dict[str, Any]) -> None:
        del payload

    def emit_bot_mood(self, payload: dict[str, Any]) -> None:
        del payload

    def emit_stream_reset(self, request_id: "str | None") -> None:
        del request_id


class NullLLMToolActionHandler:
    """No-op handler used when tool side effects are unavailable."""

    active = False

    def handle_action(
        self,
        action: str,
        payload: dict[str, Any],
    ) -> bool:
        del action
        del payload
        return False


def build_llm_workflow_event_sink(
    *,
    event_sink: LLMWorkflowEventSink | None = None,
    signal_emitter: Any = None,
) -> LLMWorkflowEventSink:
    """Return one concrete workflow event sink."""
    if event_sink is not None:
        return event_sink
    emit_signal = getattr(signal_emitter, "emit_signal", None)
    if callable(emit_signal):
        from airunner_services.llm_workflow_sinks import (
            MediatorSignalLLMWorkflowEventSink,
        )

        return MediatorSignalLLMWorkflowEventSink(signal_emitter)
    return NullLLMWorkflowEventSink()


def build_llm_tool_action_handler(
    *,
    action_handler: LLMToolActionHandler | None = None,
    signal_emitter: Any = None,
) -> LLMToolActionHandler:
    """Return one concrete tool action handler."""
    if action_handler is not None:
        return action_handler
    emit_signal = getattr(signal_emitter, "emit_signal", None)
    if callable(emit_signal):
        from airunner_services.llm_workflow_sinks import (
            MediatorSignalLLMToolActionHandler,
        )

        return MediatorSignalLLMToolActionHandler(signal_emitter)
    return NullLLMToolActionHandler()


def resolve_llm_workflow_event_sink(owner: Any) -> LLMWorkflowEventSink:
    """Resolve one workflow event sink from an owner instance."""
    signal_emitter = getattr(owner, "_signal_emitter", None)
    if signal_emitter is None and callable(
        getattr(owner, "emit_signal", None)
    ):
        signal_emitter = owner
    return build_llm_workflow_event_sink(
        event_sink=getattr(owner, "_event_sink", None),
        signal_emitter=signal_emitter,
    )


def resolve_llm_tool_action_handler(owner: Any) -> LLMToolActionHandler:
    """Resolve one tool action handler from an owner instance."""
    return build_llm_tool_action_handler(
        action_handler=getattr(owner, "_tool_action_handler", None),
    )
