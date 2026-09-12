"""Streaming mixin for WorkflowManager.

Handles workflow execution via invoke and stream methods.
"""

import uuid
from contextlib import nullcontext
from typing import Optional, Dict, Any

from langchain_core.messages import HumanMessage, AIMessage

from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger
from airunner_services.llm.managers.mixins.streaming_mixin_context import (
    StreamingMixinContext,
)

DEFAULT_WORKFLOW_RECURSION_LIMIT = 40


class StreamingMixin(StreamingMixinContext):
    """Manages workflow execution and streaming."""

    def __init__(self):
        """Initialize streaming mixin."""
        super().__init__()
        self.logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)
        self._compiled_workflow = None
        self._thread_id = "default"
        self._interrupted = False
        self._pre_prompt_knowledge = ""
        # Store current mood for attaching to AI messages
        self._current_mood = "neutral"
        self._current_emoji = "😐"
        self._current_kaomoji = "(｡◕ᴗ◕｡)"
        self._assistant_turn_index = 0

    def _prepare_workflow_run(self) -> tuple[Dict[str, Any], Any]:
        """Reset request-scoped state and return config plus math context."""
        from airunner_services.llm.agents.workflow_tools import (
            set_current_state,
        )
        from airunner_services.llm.agents.workflow_state import (
            WorkflowState as AgentWorkflowState,
        )

        self._executed_tools = []
        self._assistant_turn_index = 0

        # Bind this conversation's agent workflow state to the current asyncio
        # task context so concurrent conversations don't contaminate each other.
        if self._agent_workflow_state is None:
            self._agent_workflow_state = AgentWorkflowState()
        set_current_state(self._agent_workflow_state)

        return self._create_config(), self._get_math_context()

    def invoke(self, user_input: str) -> Dict[str, Any]:
        """Invoke the workflow with user input.

        Args:
            user_input: User's message/prompt

        Returns:
            Workflow result dictionary with 'messages' and 'tools' (list of executed tool names)
        """
        input_messages = [HumanMessage(user_input)]
        config, math_context = self._prepare_workflow_run()

        with math_context:
            result = self._compiled_workflow.invoke(
                {
                    "messages": input_messages,
                    "grounding_sources": [],
                },
                config,
            )

        # Add executed tools list to result
        result["tools"] = self._executed_tools.copy()
        return result

    def stream(
        self,
        user_input: str,
        generation_kwargs: Optional[Dict] = None,
        images: Optional[list] = None,
    ):
        """Stream the workflow execution with user input, yielding messages."""
        config, math_context = self._prepare_workflow_run()
        self._auto_learn_from_message(user_input)
        self._bind_mood_context()
        self._bind_knowledge_context()
        self._bind_social_context()
        guard = self._check_availability(user_input)
        if guard is not None:
            from langchain_core.messages import AIMessage as _AI
            yield _AI(content=guard)
            return
        self._pre_search_knowledge(user_input)

        initial_state = self._create_initial_state(
            user_input, generation_kwargs, images=images
        )

        # Inject scraped URL content as a system message so the LLM
        # sees it as part of the conversation — not background knowledge
        # it can ignore.
        url_ctx = getattr(self, "_scraped_url_context", "")
        if url_ctx:
            from langchain_core.messages import SystemMessage

            initial_state["messages"] = [
                SystemMessage(
                    content=(
                        "The user shared a URL and its content was"
                        " automatically retrieved. You have ALREADY"
                        " read it. Respond with a summary and your"
                        " thoughts on this content:\n\n" + url_ctx
                    )
                )
            ] + initial_state["messages"]

        # Seed with AI messages already in the checkpoint so we never
        # re-yield messages from prior turns when the graph state is
        # restored by the LangGraph checkpointer.
        try:
            existing_state = self._compiled_workflow.get_state(config)
            last_yielded_count = sum(
                1
                for m in (
                    existing_state.values.get("messages", [])
                    if (existing_state and existing_state.values)
                    else []
                )
                if isinstance(m, AIMessage)
            )
        except Exception:
            last_yielded_count = 0

        self._force_tool = None

        with math_context:
            for event in self._compiled_workflow.stream(
                initial_state,
                config,
                stream_mode="values",
            ):
                if self._interrupted:
                    break
                if self._has_ai_message(event):
                    new_count = self._count_ai_messages(event)
                    if new_count > last_yielded_count:
                        ai_messages = [
                            m
                            for m in event["messages"]
                            if isinstance(m, AIMessage)
                        ]
                        for i in range(last_yielded_count, new_count):
                            msg = ai_messages[i]
                            self._attach_mood(msg)
                            # Tag intermediate messages so the client can
                            # show a "thinking…" indicator while the
                            # agentic loop continues.
                            self._tag_if_thinking(msg)
                            yield msg
                        last_yielded_count = new_count

    def _create_initial_state(
        self,
        user_input: str,
        generation_kwargs: Optional[Dict],
        images: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Create initial state for workflow.

        Args:
            user_input: User's message
            generation_kwargs: Optional generation parameters
            images: Optional list of PIL Image objects for vision models

        Returns:
            Initial state dictionary
        """
        # The checkpointer handles loading existing messages from the database.
        # We only need to provide the new user message here - the add_messages
        # reducer will merge it with any existing messages from the checkpoint.

        # Create HumanMessage - multimodal if images provided
        if images and len(images) > 0:
            human_message = self._create_multimodal_message(user_input, images)
        else:
            human_message = HumanMessage(user_input)

        initial_state = {"messages": [human_message]}

        if generation_kwargs:
            initial_state["generation_kwargs"] = generation_kwargs

        return initial_state

    def _create_config(self) -> Dict[str, Any]:
        """Create workflow configuration.

        Returns:
            Configuration dictionary
        """
        return {
            "configurable": {"thread_id": self._thread_id},
            "recursion_limit": self._workflow_recursion_limit(),
        }

    def _workflow_recursion_limit(self) -> int:
        """Return the LangGraph recursion limit for the current run.

        Code-mode conversations (UwUchat's inline coding agent) raise
        the limit so the agentic loop can chain many tool calls without
        the LangGraph recursion guard firing first: each tool cycle is
        two graph supersteps (model → tools), so a 30-cycle code-mode
        ceiling needs ~65 supersteps, well above the conversational
        default of 40.  Non-code-mode conversations keep the default.
        """
        if not self._code_mode_active():
            return DEFAULT_WORKFLOW_RECURSION_LIMIT
        from airunner_services.llm.managers.mixins.node_agentic_guard import (
            CODE_MODE_MAX_AGENTIC_ITERATIONS,
        )

        # 2 supersteps per tool cycle (model → tools) plus headroom for
        # the final text-only model call and routing edges.
        return (CODE_MODE_MAX_AGENTIC_ITERATIONS * 2) + 10

    def _code_mode_active(self) -> bool:
        """Return True when the current conversation has code mode on.

        Delegates to the shared framework helper so the streaming
        config agrees with the guard, post-tool helper, prompt builder,
        and tool filter about whether the current conversation is in
        code mode.  The WorkflowManager is ``self`` here, so
        ``_conversation_id`` is directly available.
        """
        from airunner_services.llm.managers.mixins.code_mode_detection import (
            code_mode_active_for_owner,
        )

        return code_mode_active_for_owner(self)

    def _create_multimodal_message(
        self, text: str, images: list
    ) -> HumanMessage:
        """Create a multimodal HumanMessage with text and images."""
        from PIL import Image

        content = [{"type": "text", "text": text}]
        for img in images:
            if img is None:
                continue
            try:
                if isinstance(img, Image.Image):
                    content.append(self._encode_image(img))
                else:
                    self.logger.warning(
                        "Skipping non-PIL image: %s", type(img)
                    )
            except Exception as exc:
                self.logger.error("Error encoding image: %s", exc)
        self.logger.info(
            "Created multimodal message with %d image(s)", len(images)
        )
        return HumanMessage(content=content)

    @staticmethod
    def _encode_image(img) -> dict:
        """Encode a PIL Image as a base64 data URL part."""
        import base64
        import io

        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        data_url = f"data:image/png;base64,{img_base64}"
        return {"type": "image_url", "image_url": {"url": data_url}}

    def _get_math_context(self):
        """Get math executor session context manager.

        Returns:
            Context manager for math executor session or nullcontext
        """
        try:
            from airunner_services.llm.tools.math_tools import (
                math_executor_session,
            )

            session_id = f"{self._thread_id}:{uuid.uuid4()}"
            return math_executor_session(session_id)
        except ImportError:
            return nullcontext()

    def _has_ai_message(self, event: Dict) -> bool:
        """Check if event contains messages.

        Args:
            event: Stream event dictionary

        Returns:
            True if event has messages
        """
        return "messages" in event and event["messages"]

    def set_interrupted(self, value: bool) -> None:
        """Set the interrupted flag to stop generation.

        Args:
            value: True to interrupt, False to resume
        """
        self._interrupted = value
        if value:
            self.logger.info("Workflow interrupted flag set")

    def is_interrupted(self) -> bool:
        """Get interrupted flag status.

        Returns:
            True if generation is interrupted
        """
        return self._interrupted

    def get_executed_tools(self) -> list[str]:
        """Get list of tools executed in the last invocation.

        Returns:
            List of tool names that were called
        """
        return self._executed_tools.copy()
