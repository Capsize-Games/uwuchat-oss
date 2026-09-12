"""Workflow building mixin for WorkflowManager.

Handles LangGraph workflow construction and compilation.
"""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

if TYPE_CHECKING:
    pass


class WorkflowBuildingMixin:
    """Manages LangGraph workflow construction and compilation."""

    def __init__(self):
        """Initialize workflow building mixin."""
        super().__init__()
        self.logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)
        self._workflow = None
        self._compiled_workflow = None
        self._memory = None
        self._tools = []
        self._chat_model = None

    def _build_and_compile_workflow(self):
        """Build and compile the LangGraph workflow."""
        # CRITICAL: Inject WorkflowState into function globals for
        # LangGraph's get_type_hints().  Needed because LangGraph
        # introspects type hints at runtime.
        from airunner_services.llm.workflow_manager import (
            WorkflowState,
        )

        self._route_after_model.__func__.__globals__["WorkflowState"] = (
            WorkflowState
        )

        self.logger.info("Building agentic-loop workflow")
        self._workflow = self._build_graph()
        self._compiled_workflow = self._workflow.compile(
            checkpointer=self._memory
        )

    def _build_graph(self) -> StateGraph:
        """Build the agentic-loop LangGraph workflow.

        Graph topology:

            START → model → (tool_calls?) → tools → model  [loop]
                         ↘ (no tool_calls) → response → END

        When a separate response model is configured, the final
        text-only call uses that model (e.g. Haiku) instead of the
        tool-calling model (e.g. Gemini Flash).  The response node
        runs without tools, exactly once per turn.
        """
        from airunner_services.llm.workflow_manager import (
            WorkflowState,
        )

        workflow = StateGraph(WorkflowState)

        # Nodes
        workflow.add_node("model", self._call_model)
        if self._tools:
            workflow.add_node("tools", self._execute_tools_with_status)

        # When a dedicated response model is configured, add a
        # separate node that runs the expensive model once — after
        # all tool calls are complete — without any tools bound.
        if self._response_model is not None:
            self.logger.info(
                "[GRAPH] Adding response node — model: %s",
                type(self._response_model).__name__,
            )
            workflow.add_node(
                "response", self._call_response_model
            )
        else:
            self.logger.info(
                "[GRAPH] No response_model — using legacy single-model path"
            )

        # Entry
        workflow.add_edge(START, "model")

        if self._tools:
            if self._response_model is not None:
                # model → tools or response
                workflow.add_conditional_edges(
                    "model",
                    self._route_after_model,
                    {"tools": "tools", "response": "response"},
                )
                # tools → model (agentic loop)
                workflow.add_edge("tools", "model")
                # response → END
                workflow.add_edge("response", END)
            else:
                # model → tools or END (legacy single-model path)
                workflow.add_conditional_edges(
                    "model",
                    self._route_after_model,
                    {"tools": "tools", "end": END},
                )
                workflow.add_edge("tools", "model")
        else:
            workflow.add_edge("model", END)

        return workflow
