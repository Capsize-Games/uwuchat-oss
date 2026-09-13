"""Service-owned LangGraph workflow manager."""

import uuid
from typing import Any, Annotated, Callable, List, Optional

from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.graph import add_messages
from typing_extensions import TypedDict

from airunner_services.llm.managers.database_checkpoint_saver import (
    DatabaseCheckpointSaver,
)
from airunner_services.llm.managers.mixins.node_functions_mixin import (
    NodeFunctionsMixin,
)
from airunner_services.llm.managers.mixins.streaming_mixin import (
    StreamingMixin,
)
from airunner_services.llm.managers.mixins.system_prompt_mixin import (
    SystemPromptMixin,
)
from airunner_services.llm.managers.mixins.tool_execution_mixin import (
    ToolExecutionMixin,
)
from airunner_services.llm.managers.mixins.tool_management_mixin import (
    ToolManagementMixin,
)
from airunner_services.llm.managers.mixins.workflow_building_mixin import (
    WorkflowBuildingMixin,
)
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.llm_workflow_events import (
    LLMWorkflowEventSink,
    build_llm_workflow_event_sink,
)
from airunner_services.utils.application import get_logger


MAX_AGENTIC_ITERATIONS = 6
"""Maximum tool-call cycles before forcing a text-only final response."""


class WorkflowState(TypedDict, total=False):
    """LangGraph state schema for the conversation workflow.

    Note: a second WorkflowState exists in agents/workflow_state.py — that one
    is a dataclass tracking multi-step task phases and TODOs. It is owned by
    WorkflowManager (self._agent_workflow_state) and bound to the async-task
    context via a ContextVar before each invocation. The two types are separate
    by design: this TypedDict drives LangGraph message passing; the dataclass
    drives tool-level workflow logic.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    generation_kwargs: dict[str, Any]
    workflow_continuation: bool
    # Mood state: written by update_mood tool and auto-mood logic; read by
    # get_current_mood() to avoid O(n) message-scanning on every prompt build.
    current_mood: Optional[dict]
    # Placeholder so LangGraph state can carry the agent workflow reference
    # if needed for InjectedState migration (see task 3.2 / audit todo).
    agent_workflow: Optional[Any]
    # Agentic loop counter: incremented each time the model calls tools.
    # When this exceeds MAX_AGENTIC_ITERATIONS, the next model call
    # is forced to produce a text-only response (tools stripped).
    loop_count: int
    # Grounding sources accumulated from search tool results this turn.
    # Written by _stash_grounding_sources after each ToolNode invocation;
    # read by the tools node to repopulate the ContextVar before the next
    # ToolNode.invoke() so check_grounding sees them regardless of any
    # context boundaries between graph nodes.
    grounding_sources: list[str]


class WorkflowManager(
    ToolManagementMixin,
    ToolExecutionMixin,
    WorkflowBuildingMixin,
    SystemPromptMixin,
    NodeFunctionsMixin,
    StreamingMixin,
):
    """Manage the LangGraph workflow for agent execution."""

    def __init__(
        self,
        system_prompt: str,
        chat_model: Any,
        tools: Optional[List[Callable]] = None,
        max_history_tokens: int = 8000,
        conversation_id: Optional[int] = None,
        llm_settings: Optional[Any] = None,
        chatbot: Optional[Any] = None,
        event_sink: Optional[LLMWorkflowEventSink] = None,
        signal_emitter: Optional[Any] = None,
        response_model: Optional[Any] = None,
        tool_manager: Optional[Any] = None,
    ):
        super().__init__()

        self.logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

        self._system_prompt = system_prompt
        self._original_chat_model = chat_model
        self._chat_model = chat_model
        self._response_model = response_model
        self._tools = tools or []
        # Reference to the owning LLM manager's ToolManager, so
        # ForcedToolExecutionPolicy can look up a forced tool (e.g.
        # check_grounding) by name when it isn't part of the current
        # turn's filtered tool set. See _ensure_forced_tool_available.
        self._tool_manager = tool_manager
        self._max_history_tokens = max_history_tokens
        self._token_counter = lambda msgs: count_tokens_approximately(msgs)
        self._conversation_id = conversation_id
        self._memory = DatabaseCheckpointSaver(
            conversation_id,
            ephemeral=(conversation_id is None),
            max_history_tokens=max_history_tokens,
        )
        self._response_format = None
        self._force_tool = None
        self._current_request_id: Optional[str] = None

        self.llm_settings = llm_settings
        self.chatbot = chatbot
        self._event_sink = build_llm_workflow_event_sink(
            event_sink=event_sink,
            signal_emitter=signal_emitter,
        )
        self._signal_emitter = signal_emitter
        self._thread_id = (
            str(conversation_id) if conversation_id else str(uuid.uuid4())
        )

        self._workflow = None
        self._compiled_workflow = None
        self._token_callback: Optional[Callable[[str], None]] = None
        self._thinking_callback: Optional[Callable[[str, str], None]] = None
        self._interrupted = False
        self._executed_tools: list[str] = []
        # Dynamic per-turn context (datetime, mood, preflight, rag) set by
        # setup_generation_workflow() before each call and injected into the
        # human turn so the system prompt prefix cache is never invalidated.
        self._per_turn_context: str = ""
        # Per-conversation agent workflow state for multi-step tasks.
        # Set on the ContextVar before each LangGraph invocation so concurrent
        # conversations cannot share or corrupt each other's state.
        self._agent_workflow_state = None

        self._initialize_model()
        self._build_and_compile_workflow()

    def clear_memory(self):
        """Clear the conversation memory and checkpoint state."""
        self._memory.message_history.clear()

        if hasattr(self._memory, "clear_checkpoints"):
            self._memory.clear_checkpoints()

        self._build_and_compile_workflow()

    def set_conversation_id(
        self,
        conversation_id: int,
        ephemeral: bool = False,
        force_rebuild: bool = False,
    ):
        """Set the conversation ID used for persistence.

        Only updates memory and thread_id — does not recompile the LangGraph
        unless force_rebuild is True or the compiled workflow doesn't exist yet.
        Recompiling on every conversation switch is expensive and unnecessary
        since the graph topology (model, tools, system prompt) hasn't changed.
        """
        self._conversation_id = conversation_id
        self._thread_id = str(conversation_id)

        self._memory = DatabaseCheckpointSaver(
            conversation_id,
            ephemeral=ephemeral,
            max_history_tokens=self._max_history_tokens,
        )

        if force_rebuild or self._compiled_workflow is None:
            self._build_and_compile_workflow()
        else:
            # Reattach the new checkpointer to the already-compiled workflow
            # without triggering a full LangGraph recompile.
            self._compiled_workflow = self._workflow.compile(
                checkpointer=self._memory
            )

    def update_system_prompt(self, system_prompt: str):
        """Update the system prompt and rebuild the workflow."""
        self.logger.debug(
            "Updating system prompt to: %s...", system_prompt[:200]
        )
        self._system_prompt = system_prompt
        self._build_and_compile_workflow()

    def update_prompt_segments(self, segments) -> None:
        """Store pre-computed PromptSegments for Claude multi-breakpoint
        caching.  Set by apply_workflow_request_setup with the real
        per-turn action, so _build_claude_prompt can read them without
        recomputing or hardcoding the action."""
        self._prompt_segments = segments

    def set_response_format(self, response_format: Optional[str]):
        """Set the expected response format after tool execution."""
        self._response_format = response_format
        self.logger.debug("Response format set to: %s", response_format)

    def set_force_tool(self, force_tool: Optional[str]):
        """Set the forced tool for agentic research mode."""
        self._force_tool = force_tool
        self.logger.debug("Force tool set to: %s", force_tool)

    def set_token_callback(
        self,
        callback: Optional[Callable[[str], None]],
    ) -> None:
        """Register a callback for streaming tokens during execution."""
        self._token_callback = callback

    def set_thinking_callback(
        self,
        callback: Optional[Callable[[str, str], None]],
    ) -> None:
        """Register a callback for streaming thinking events.

        The callback receives ``(status, content)`` where ``status`` is one of
        ``"started"``, ``"streaming"``, or ``"completed"``. It is used by the
        daemon NDJSON path to publish typed ``message_type='thinking'`` chunks.
        """
        self._thinking_callback = callback

    def set_request_id(self, request_id: Optional[str]) -> None:
        """Set the active request ID for request-scoped UI signals."""
        self._current_request_id = request_id


__all__ = ["WorkflowManager", "WorkflowState", "MAX_AGENTIC_ITERATIONS"]
