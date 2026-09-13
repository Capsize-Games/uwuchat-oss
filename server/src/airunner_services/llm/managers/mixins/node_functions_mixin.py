"""Node functions mixin for WorkflowManager."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from langchain_core.messages import BaseMessage

from airunner_services.llm.managers.mixins.node_forced_response_helper import (
    NodeForcedResponseHelper,
)
from airunner_services.llm.managers.mixins.node_post_tool_instructions_helper import (
    NodePostToolInstructionsHelper,
)
from airunner_services.llm.managers.mixins.node_prompt_assembly_helper import (
    NodePromptAssemblyHelper,
)
from airunner_services.llm.managers.mixins.node_response_generation_helper import (
    NodeResponseGenerationHelper,
)
from airunner_services.llm.managers.mixins.node_streaming_response_helper import (
    NodeStreamingResponseHelper,
)
from airunner_services.llm.managers.route_policy import RoutePolicy

if TYPE_CHECKING:
    from airunner_services.llm.workflow_manager import WorkflowState


class NodeFunctionsMixin:
    """Implements LangGraph node functions for the workflow."""

    WORKFLOW_TOOLS = {
        "start_workflow",
        "transition_phase",
        "add_todo_item",
        "start_todo_item",
        "complete_todo_item",
        "get_workflow_status",
    }

    def _get_route_policy(self) -> RoutePolicy:
        """Return the cached route-policy helper."""
        helper = getattr(self, "_route_policy_helper", None)
        if helper is None:
            helper = RoutePolicy(self)
            self._route_policy_helper = helper
        return helper

    def _get_response_generation_helper(self) -> NodeResponseGenerationHelper:
        """Return the cached response-generation helper."""
        helper = getattr(self, "_response_generation_helper", None)
        if helper is None:
            helper = NodeResponseGenerationHelper(self)
            self._response_generation_helper = helper
        return helper

    def _get_streaming_response_helper(self) -> NodeStreamingResponseHelper:
        """Return the cached streaming-response helper."""
        helper = getattr(self, "_streaming_response_helper", None)
        if helper is None:
            helper = NodeStreamingResponseHelper(self)
            self._streaming_response_helper = helper
        return helper

    def _get_prompt_assembly_helper(self) -> NodePromptAssemblyHelper:
        """Return the cached prompt-assembly helper."""
        helper = getattr(self, "_prompt_assembly_helper", None)
        if helper is None:
            helper = NodePromptAssemblyHelper(self)
            self._prompt_assembly_helper = helper
        return helper

    def _get_post_tool_instructions_helper(
        self,
    ) -> NodePostToolInstructionsHelper:
        """Return the cached post-tool instruction helper."""
        helper = getattr(self, "_post_tool_instructions_helper", None)
        if helper is None:
            helper = NodePostToolInstructionsHelper(self)
            self._post_tool_instructions_helper = helper
        return helper

    def _get_forced_response_helper(self) -> NodeForcedResponseHelper:
        """Return the cached forced-response helper."""
        helper = getattr(self, "_forced_response_helper", None)
        if helper is None:
            helper = NodeForcedResponseHelper(self)
            self._forced_response_helper = helper
        return helper

    def _force_response_node(self, state: "WorkflowState") -> Dict[str, Any]:
        """Generate one forced response when redundancy is detected."""
        return self._get_forced_response_helper().force_response_node(state)

    def _has_tool_calls(self, message: BaseMessage) -> bool:
        """Return whether one message contains tool calls."""
        return self._get_forced_response_helper().has_tool_calls(message)

    def _get_tool_messages(self, messages: List[BaseMessage]) -> List[Any]:
        """Return the tool messages from one message list."""
        return self._get_forced_response_helper().get_tool_messages(messages)

    def _should_return_tool_direct(self, tool_name: str) -> bool:
        """Return whether one bound tool should bypass the model pass."""
        return self._get_forced_response_helper().should_return_tool_direct(
            tool_name
        )

    def _stream_model_response(
        self,
        prompt: List[BaseMessage],
        generation_kwargs: Optional[Dict] = None,
    ) -> str:
        """Stream one model response and preserve response metadata."""
        return self._get_response_generation_helper().stream_model_response(
            prompt,
            generation_kwargs,
        )

    # ========================================================================
    # ROUTE AFTER MODEL
    # ========================================================================

    def _route_after_model(self, state: "WorkflowState") -> str:
        """Route to tools when model made tool calls, else end.

        In the agentic loop the model alone decides whether to call tools.
        """
        return self._get_route_policy().after_model(state)

    def _call_model(self, state: "WorkflowState") -> Dict[str, Any]:
        """Call the tool-calling model with trimmed message history.

        Live token streaming is left enabled unconditionally.
        Native tool-calling means pure tool-call chunks already
        carry empty ``content`` fields, so ``_process_chunk`` /
        ``store_visible_text`` naturally skip them without any
        outer suppression.

        When this specific call streamed visible content AND the
        model still ended up with tool calls on its final message
        (the rare interleaved-narration case), a stream-reset is
        emitted so the client discards the intermediate text before
        the tool loop continues.
        """
        self._current_node_phase = "DIALOGUE"
        self._current_model_info = _capture_model_info(
            self._chat_model, "DIALOGUE"
        )
        # Reset per-call streaming flag + narration counter so they
        # reflect only this call (narration length feeds tool-event
        # position stashing for inline widget placement on reload).
        self._streamed_content = False
        self._narration_length = 0
        result = self._get_prompt_assembly_helper().call_model(state)
        messages = result.get("messages", [])
        has_tool_calls = False
        if messages:
            msg = messages[-1]
            has_tool_calls = bool(getattr(msg, "tool_calls", None))
        self.logger.debug(
            "[CALL_MODEL diag] tools_bound=%s has_tool_calls=%s "
            "streamed_content=%s",
            bool(self._tools), has_tool_calls, self._streamed_content,
        )
        # Narrow safety net: model streamed visible text AND called
        # a tool in the same turn — emit a stream-reset so the client
        # discards the intermediate narration before tool execution.
        if has_tool_calls and self._streamed_content:
            self._reset_stream_for_tool_call()
        return result

    def _reset_stream_for_tool_call(self) -> None:
        """Emit a stream-reset and clear accumulated text when the model
        streamed narration AND called a tool in the same call."""
        request_id = getattr(self, "_current_request_id", None)
        if request_id and self._event_sink:
            try:
                self._event_sink.emit_stream_reset(request_id)
                self.logger.info(
                    "[CALL_MODEL diag] stream_reset emitted "
                    "request_id=%s", request_id,
                )
            except Exception:
                pass
        reset_fn = getattr(self, "_reset_stream_state", None)
        if callable(reset_fn):
            reset_fn()

    def _call_response_model(
        self, state: "WorkflowState"
    ) -> Dict[str, Any]:
        """Generate the final response using the dedicated response model.

        Swaps _chat_model to the expensive response model (e.g. Haiku),
        strips all tools, and calls the model once.  This runs AFTER
        the tool-calling loop is complete and the response model is
        never asked to call tools.
        """
        self._current_node_phase = "RESPONSE"
        self._current_model_info = _capture_model_info(
            self._response_model, "RESPONSE"
        )
        prev = self._chat_model
        prev_orig = self._original_chat_model
        # Strip the tool model's last AIMessage so only Haiku's
        # response is shown.  Without this, Gemini's text and
        # Haiku's text both appear as duplicate responses.
        state = dict(state)
        msgs = list(state.get("messages", []))
        if msgs and msgs[-1].__class__.__name__ == "AIMessage":
            stripped = msgs.pop()
            self.logger.info(
                "[STRIP] Removed tool model AIMessage (%d chars)",
                len(str(getattr(stripped, "content", "")))
            )
            state["messages"] = msgs
        try:
            self.logger.info(
                "[SWAP] call_response: swapping %s → %s",
                getattr(prev, "model_name", "?"),
                getattr(self._response_model, "model_name", "?"),
            )
            self._chat_model = self._response_model
            self._original_chat_model = self._response_model
            self._unbind_tools_from_model()
            return self._get_prompt_assembly_helper().call_model(state)
        finally:
            self._chat_model = prev
            self._original_chat_model = prev_orig
            self._unbind_tools_from_model()
            if self._tools:
                self._bind_tools_to_model()


def _capture_model_info(chat_model, pipeline_key: str) -> dict:
    """Extract model identity metadata from a chat model binding."""
    model_id = (
        getattr(chat_model, "model", None)
        or getattr(chat_model, "model_name", "")
    )
    provider = ""
    if hasattr(chat_model, "provider"):
        provider = str(getattr(chat_model, "provider", ""))
    elif "/" in str(model_id) and model_id:
        provider = str(model_id).split("/")[0]
    return {
        "model_id": str(model_id),
        "provider": provider,
        "pipeline_key": pipeline_key,
    }
