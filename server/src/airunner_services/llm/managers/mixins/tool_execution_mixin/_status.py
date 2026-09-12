"""Status emission and mood restore for ToolExecutionMixin."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from airunner_services.llm_workflow_events import (
    resolve_llm_workflow_event_sink,
)
from airunner_services.utils.application.log_hygiene import summarize_text

if TYPE_CHECKING:  # pragma: no cover - import-time type-only block
    from langchain_core.messages import ToolMessage

    from airunner_services.llm.workflow_manager import WorkflowState


class ToolExecutionStatusMixin:
    """Emit tool status signals and restore post-tool mood state."""

    def _sanitize_tool_functions(self) -> None:
        """Ensure each tool function has a docstring.

        LangChain's StructuredTool.from_function raises ValueError if a function
        lacks both a description and a docstring. Some legacy mixin tools created
        via @tool (langchain.tools) may omit docstrings. This method adds a minimal
        docstring dynamically to prevent runtime failures.
        """
        sanitized = 0
        for func in self._tools:
            # Skip if already documented
            if getattr(func, "__doc__", None):
                continue
            # Attempt to use .description attribute if present
            desc = (
                getattr(func, "description", None)
                or f"Tool function '{getattr(func, 'name', func.__name__)}' automatically documented."
            )
            func.__doc__ = desc  # type: ignore
            sanitized += 1
        if sanitized:
            self.logger.debug(
                "Added fallback docstrings to %d tool(s) missing documentation",
                sanitized,
            )

    def _emit_starting_status(self, tool_calls: list):
        """Emit starting status signals for tool calls.

        Args:
            tool_calls: List of tool call dictionaries
        """
        event_sink = resolve_llm_workflow_event_sink(self)

        for tool_call in tool_calls:
            tool_name = tool_call.get("name", "unknown")
            tool_args = tool_call.get("args", {})
            tool_id = tool_call.get("id", "")

            # Track this tool execution
            self._executed_tools.append(tool_name)

            query = self._extract_query_from_args(tool_args)

            self.logger.info(
                "Tool starting: %s (%s)",
                tool_name,
                summarize_text(query, label="query"),
            )

            event_sink.emit_tool_status(
                {
                    "tool_id": tool_id,
                    "tool_name": tool_name,
                    "query": query,
                    "status": "starting",
                    "details": None,
                    "conversation_id": self._conversation_id,
                    "request_id": getattr(self, "_current_request_id", None),
                    "timestamp": str(datetime.now()),
                }
            )

    def _emit_completed_status(
        self, result_state: WorkflowState, tool_calls: list
    ):
        """Emit completed status signals for tool results.

        Args:
            result_state: Workflow state after tool execution
            tool_calls: List of original tool call dictionaries
        """
        from langchain_core.messages import ToolMessage

        event_sink = resolve_llm_workflow_event_sink(self)

        new_messages = result_state.get("messages", [])
        for msg in new_messages:
            if isinstance(msg, ToolMessage):
                matching_tool_call = self._find_matching_tool_call(
                    msg.tool_call_id, tool_calls
                )
                if matching_tool_call:
                    self._emit_one_tool_result(msg, matching_tool_call, event_sink)

    def _emit_one_tool_result(
        self,
        msg: ToolMessage,
        matching_tool_call: dict,
        event_sink,
    ) -> None:
        """Emit status for one completed ToolMessage."""
        tool_name = matching_tool_call.get("name", "unknown")
        tool_args = matching_tool_call.get("args", {})
        query = self._extract_query_from_args(tool_args)

        # Extract details from result (URLs, sources, etc.)
        details = self._extract_tool_details(tool_name, msg.content)
        status = (
            "error"
            if self._is_tool_error_result(msg.content)
            else "completed"
        )

        self.logger.info(
            f"Tool {status}: {tool_name} - {details if details else 'success'}"
        )

        event_sink.emit_tool_status(
            {
                "tool_id": msg.tool_call_id,
                "tool_name": tool_name,
                "query": query,
                "status": status,
                "details": details,
                "conversation_id": self._conversation_id,
                "request_id": getattr(self, "_current_request_id", None),
                "timestamp": str(datetime.now()),
            }
        )
        # Guarantee the tool output reaches the streaming consumer (and
        # thus the WebSocket) regardless of whether the workflow event
        # sink is wired — see _emit_tool_result_stream.
        self._emit_tool_result_stream(
            msg.tool_call_id,
            tool_name,
            query,
            details,
            status,
        )

    def _emit_tool_result_stream(
        self,
        tool_id: str,
        tool_name: str,
        query: str,
        details: str | None,
        status: str = "completed",
    ) -> None:
        """Push one tool-result marker into the LLM text stream.

        Uses the same LLMResponse(message_type="tool_status") shape the
        workflow sink injects, but sent through the owner's direct
        stream-signal path so it reaches the runtime's response queue
        (and therefore the WebSocket) even when the event sink is a
        no-op.  Never propagates failures.
        """
        try:
            import json as _json

            from airunner_services.llm.llm_response import LLMResponse

            response = LLMResponse(
                message=_json.dumps(
                    {
                        "tool_id": tool_id,
                        "tool_name": tool_name,
                        "status": status,
                        "details": details,
                        "query": query,
                    }
                ),
                message_type="tool_status",
                is_end_of_message=False,
                request_id=getattr(self, "_current_request_id", None),
            )
            send = getattr(self, "send_llm_text_streamed_signal", None)
            if callable(send):
                send(response)
            from ._event_stash import stash_tool_event

            stash_tool_event(self, tool_id, tool_name, query, details, status)
        except (TypeError, ValueError) as exc:
            self.logger.warning(
                "Failed to stream tool result for %s: %s", tool_name, exc,
            )

    def _maybe_restore_mood_state(self, result_state: WorkflowState) -> None:
        """Read update_mood's payload from the ContextVar and restore
        current_mood in the LangGraph state.

        The update_mood tool can no longer return ``Command(update=...)``
        because LangGraph >=1.0.10 requires every Command to include a
        ToolMessage in ``update.messages`` — something the tool cannot
        produce without the ``tool_call_id``.  The tool now stashes the
        payload in a ContextVar and returns a plain string; we read it
        back here and write it into the output state.
        """
        try:
            from airunner_services.llm.tools.mood_tools import (
                get_last_mood_payload,
            )

            payload = get_last_mood_payload()
            self.logger.warning(
                "[MOOD DEBUG] _maybe_restore_mood_state payload=%r",
                payload,
            )
            if payload is not None:
                result_state["current_mood"] = payload
                # Keep the cached mood/emoji on the StreamingMixin
                # up-to-date so _attach_mood() picks up the latest
                # values instead of always returning "neutral" / "😐".
                self._current_mood = payload.get("mood", "neutral")
                self._current_emoji = payload.get("emoji", "😐")
                self._current_kaomoji = payload.get(
                    "kaomoji", "(｡◕ᴗ◕｡)"
                )
                # Override the pending mood set by do_generate() with the
                # model's explicit self-report, so add_message() attaches
                # this more specific mood to the turn's assistant message
                # instead of the earlier auto-computed one.
                _memory = getattr(self, "_memory", None)
                if _memory:
                    msg_hist = getattr(_memory, "message_history", None)
                    if msg_hist is not None:
                        msg_hist._pending_bot_mood = payload
                # Re-emit through the event sink to guarantee the mood
                # reaches the client even when the original signal from
                # the tool body does not route through the pending-
                # request queue in cloud deployment.
                event_sink = getattr(self, "_event_sink", None)
                if event_sink is not None:
                    event_sink.emit_bot_mood(payload)
        except Exception as exc:
            self.logger.exception(
                "[MOOD DEBUG] _maybe_restore_mood_state FAILED: %s", exc,
            )
