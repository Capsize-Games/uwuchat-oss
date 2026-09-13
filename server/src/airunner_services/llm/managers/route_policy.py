"""Route-policy helpers for the agentic LangGraph workflow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage

if TYPE_CHECKING:
    from airunner_services.llm.workflow_manager import WorkflowState


class RoutePolicy:
    """Compute post-node routing decisions for the agentic loop."""

    def __init__(self, owner: Any) -> None:
        """Cache the owning workflow manager."""
        self._owner = owner

    def after_model(self, state: "WorkflowState") -> str:
        """Route to tools when the model made tool calls, else end.

        In the agentic loop the model alone decides when to call tools and
        when to respond.  No pre-classification, no forced synthesis path.
        """
        last_message: AIMessage = state["messages"][-1]  # type: ignore[assignment]
        if getattr(last_message, "tool_calls", None):
            self._owner.logger.info(
                "[ROUTE] model has tool calls → tools"
            )
            return "tools"
        # When a dedicated response model is configured, route to it
        # instead of ending — the response node runs Haiku without
        # tools.  The tool model's text is stripped in
        # _call_response_model so only Haiku's output is shown.
        if self._owner._response_model is not None:
            self._owner.logger.info(
                "[ROUTE] model has text → response model"
            )
            return "response"
        self._owner.logger.info("[ROUTE] model has text only → end")
        return "end"
