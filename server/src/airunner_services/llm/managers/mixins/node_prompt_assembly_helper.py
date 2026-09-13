"""Prompt-assembly helpers for node functions.

Core call_model logic and agentic-loop iteration guard.
build_prompt → node_prompt_builder_mixin.py
knowledge/vision → node_prompt_context_mixin.py
echo detection → node_prompt_echo_mixin.py
"""

from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import AIMessage, BaseMessage

from airunner_services.llm.managers.mixins.node_prompt_assembly_tools import (
    NodePromptAssemblyToolsMixin,
)
from airunner_services.llm.managers.mixins.node_prompt_builder_mixin import (
    NodePromptBuilderMixin,
)
from airunner_services.llm.managers.mixins.node_prompt_context_mixin import (
    NodePromptContextMixin,
)
from airunner_services.llm.managers.mixins.node_prompt_echo_mixin import (
    NodePromptEchoMixin,
)
from airunner_services.llm.managers.mixins.node_prompt_write_only_strip import (
    _strip_write_only_tool_pairs,
)


class NodePromptAssemblyHelper(
    NodePromptAssemblyToolsMixin,
    NodePromptBuilderMixin,
    NodePromptContextMixin,
    NodePromptEchoMixin,
):
    """Build prompts and model-call inputs for workflow nodes."""

    def __init__(self, owner) -> None:
        """Store the owning workflow manager."""
        self._owner = owner

    # ------------------------------------------------------------------
    # Main entry point — called from node_functions_mixin._call_model
    # ------------------------------------------------------------------

    def call_model(self, state) -> Dict[str, Any]:
        """Call the model, enforcing the agentic loop iteration limit."""
        self._log_recent_messages(state["messages"])
        generation_kwargs = state.get("generation_kwargs", {})
        self._log_model_info()
        trimmed = self._get_trimmed_messages(state["messages"])
        # Compute loop_count BEFORE write-only tool stripping so
        # ToolMessages from tools like record_knowledge /
        # record_character_fact are still visible for counting.
        loop_count = self._compute_loop_count(state, trimmed)
        trimmed = _strip_write_only_tool_pairs(trimmed)
        if self._get_agentic_guard().is_at_max_cycles(
            {"loop_count": loop_count}
        ):
            return self._get_agentic_guard().force_final_response(
                trimmed, generation_kwargs
            )

        is_mid_loop = self._has_tool_messages_in(trimmed)
        prompt = self.build_prompt(trimmed)
        self._owner._assistant_turn_index = (
            getattr(self._owner, "_assistant_turn_index", 0) + 1
        )
        response = self._generate(prompt, generation_kwargs)
        usage = getattr(response, "usage_metadata", None)
        self._owner.logger.info(
            "[RECORD_ITER] loop=%d has_usage=%s usage=%s",
            loop_count,
            usage is not None,
            list(usage.keys()) if isinstance(usage, dict) else None,
        )
        self._record_iteration_usage(response, loop_count)
        response = self._ensure_response(response)
        if not is_mid_loop:
            response = self._check_echo_and_retry(
                response, prompt, state, generation_kwargs
            )
        response = self._prepend_tool_call_xml(
            response, state["messages"]
        )
        return {"messages": [response], "loop_count": loop_count}

    # ------------------------------------------------------------------
    # Agentic loop helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_loop_count(
        state: Dict[str, Any],
        trimmed: List[BaseMessage],
    ) -> int:
        """Increment loop_count when tool results are present."""
        loop_count = state.get("loop_count", 0)
        has_tool_results = any(
            msg.__class__.__name__ == "ToolMessage"
            for msg in trimmed
        )
        return loop_count + 1 if has_tool_results else loop_count

    @staticmethod
    def _has_tool_messages_in(
        messages: List[BaseMessage],
    ) -> bool:
        """Return True when any message is a ToolMessage."""
        return any(
            msg.__class__.__name__ == "ToolMessage"
            for msg in messages
        )

    def _generate(
        self,
        prompt: Any,
        generation_kwargs: Dict[str, Any],
    ) -> AIMessage:
        """Generate one response through the current model."""
        return (
            self._owner._get_response_generation_helper()
            .generate_response(prompt, generation_kwargs)
        )

    def _get_agentic_guard(self):
        """Return the cached agentic iteration guard."""
        guard = getattr(self, "_agentic_guard", None)
        if guard is None:
            from airunner_services.llm.managers.mixins.node_agentic_guard import (
                NodeAgenticGuard,
            )
            guard = NodeAgenticGuard(self._owner)
            self._agentic_guard = guard
        return guard

    # ------------------------------------------------------------------
    # Model info logging
    # ------------------------------------------------------------------

    def _log_model_info(self) -> None:
        """Log the active model name and RP mode for debugging."""
        chat_model = getattr(self._owner, "_chat_model", None)
        model_name = (
            getattr(chat_model, "model", None)
            or getattr(chat_model, "model_name", None)
            or "unknown"
        )
        from airunner_services.llm.managers.prompt_builder.identity_parts import (
            _is_rp_mode,
        )
        self._owner.logger.info(
            "[PROMPT] call_model start: model=%s messages=%d "
            "is_rp_mode=%s",
            model_name,
            len(getattr(self._owner, "_memory", type).__dict__),
            _is_rp_mode(self._owner),
        )

    # ------------------------------------------------------------------
    # Message utilities
    # ------------------------------------------------------------------

    def _log_recent_messages(
        self, messages: List[BaseMessage]
    ) -> None:
        """Log message counts and types (no content) for debugging."""
        self._owner.logger.info(
            "[CALL MODEL DEBUG] Total messages in state: %s",
            len(messages),
        )
        type_counts: dict[str, int] = {}
        for msg in messages:
            t = type(msg).__name__
            type_counts[t] = type_counts.get(t, 0) + 1
        self._owner.logger.info(
            "[CALL MODEL DEBUG] Message types: %s", type_counts
        )

    def _ensure_response(self, response: Any) -> AIMessage:
        """Return a non-None response, emitting a fallback if needed."""
        if response is not None:
            # Qwen-family local daemons emit tool calls as JSON inside
            # the message content ({"tool_call": {...}}) instead of an
            # OpenAI tool_calls array.  Materialize them so the route
            # policy sees real tool_calls and the agentic loop executes
            # the tool instead of narrating it.  No-op when the message
            # has native tool_calls or no embedded JSON.
            from airunner_services.llm.managers.mixins.embedded_tool_calls import (
                materialize_embedded_tool_calls,
            )

            return materialize_embedded_tool_calls(response)
        self._owner.logger.error(
            "[CALL MODEL DEBUG] Model returned no message; "
            "emitting fallback AIMessage"
        )
        return AIMessage(
            content="We are experiencing an outage, "
            "please try again later.",
            additional_kwargs={"error": "no_message_generated"},
            tool_calls=[],
        )

    @staticmethod
    def _prepend_tool_call_xml(
        response: AIMessage,
        messages: List[BaseMessage],
    ) -> AIMessage:
        """Prepend prior tool_call XML to a response content."""
        content = str(getattr(response, "content", "") or "")
        if not content or "<tool_call>" in content:
            return response
        for prev in reversed(messages):
            if hasattr(prev, "tool_calls") and prev.tool_calls:
                src = str(getattr(prev, "content", "") or "")
                if "<tool_call>" in src:
                    return AIMessage(
                        content=src + "\n" + content,
                        additional_kwargs=getattr(
                            response,
                            "additional_kwargs",
                            {},
                        )
                        or {},
                        tool_calls=[],
                    )
                break
        return response

    def _record_iteration_usage(
        self, response: AIMessage, iteration: int
    ) -> None:
        """Record token usage for one ReAct loop iteration."""
        try:
            usage = getattr(response, "usage_metadata", None) or {}
            inp = int(usage.get("input_tokens", 0)
                      or usage.get("prompt_tokens", 0) or 0)
            out = int(usage.get("output_tokens", 0)
                      or usage.get("completion_tokens", 0) or 0)
            if inp == 0 and out == 0:
                return
            from airunner_services.data.tenant import get_tenant_key
            from airunner_services.llm.managers.mixins.generation_usage \
                import cache_read_tokens_from_usage
            from airunner_services.llm.token_usage import (
                record_usage,
            )
            from airunner_services.llm.pipeline_loader import (
                pipeline_config,
            )
            from airunner_services.llm.active_call_chain import (
                get_active_call_chain,
            )
            cfg = pipeline_config("DIALOGUE")
            chat_model = getattr(self._owner, "_chat_model", None)
            model_id = (
                getattr(chat_model, "model", None)
                or cfg.get("model", "")
            )
            record_usage(
                pipeline_key=f"DIALOGUE (turn {iteration})",
                model_id=model_id,
                input_tokens=inp,
                output_tokens=out,
                cache_read_tokens=cache_read_tokens_from_usage(usage),
                tenant_key=get_tenant_key(),
                call_chain_id=(
                    getattr(self._owner, "_call_chain_id", None)
                    or get_active_call_chain()
                ),
            )
        except Exception:
            pass
