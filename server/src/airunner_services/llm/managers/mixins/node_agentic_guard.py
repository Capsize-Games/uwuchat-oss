"""Iteration guard for the agentic tool-calling loop.

When the model has cycled through tools too many times without producing
a text-only response, this guard strips tool access and forces a final
answer that keeps the collected tool results in context.

Code mode (UwUchat's inline coding-agent conversations) gets a higher
ceiling: a multi-file coding task routinely needs many more than the
conversational default of 6 tool cycles (exploration + reads + edits +
verification).  The ceiling is raised for the whole code-mode
conversation, mirroring how headlesscode's own harness uses 250
iterations for the same reason.
"""

from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from airunner_services.llm.workflow_manager import MAX_AGENTIC_ITERATIONS

# Code-mode conversations get a much higher ceiling than the generic
# conversational default: real coding tasks (grep → read → edit →
# verify) routinely need dozens of tool cycles.  Must stay under
# DEFAULT_WORKFLOW_RECURSION_LIMIT (40) — see streaming_mixin.py — so
# the LangGraph recursion guard never fires before this one.
CODE_MODE_MAX_AGENTIC_ITERATIONS = 30

_STOP_TOOLS_INSTRUCTION = (
    "\n\n[You have called tools {count} times. "
    "Do not call any more tools. "
    "Answer the user now based on everything you have learned.]"
)

_IN_CHARACTER_FALLBACK = (
    "I'm sorry, but I wasn't able to process that properly. "
    "Could you try asking again?"
)


class NodeAgenticGuard:
    """Enforce the max-iteration limit in the agentic tool-call loop."""

    def __init__(self, owner: Any) -> None:
        """Cache the owning workflow manager."""
        self._owner = owner

    @staticmethod
    def count_tool_cycles(messages: List[BaseMessage]) -> int:
        """Return the number of complete tool-invocation cycles."""
        count = 0
        for msg in messages:
            if getattr(msg, "tool_calls", None):
                count += 1
        return count

    def _code_mode_active(self) -> bool:
        """Return True when the current conversation has code mode on.

        Delegates to the shared framework helper so the guard agrees
        with the post-tool helper, prompt builder, tool filter, and
        streaming config about whether the current conversation is in
        code mode.  Any import error or non-UwUchat deployment returns
        False — a pure no-op.
        """
        from airunner_services.llm.managers.mixins.code_mode_detection import (
            code_mode_active_for_owner,
        )

        return code_mode_active_for_owner(self._owner)

    def is_at_max_cycles(self, state: Dict[str, Any]) -> bool:
        """Return True when tool cycles have reached the limit."""
        loop_count = state.get("loop_count", 0)
        return loop_count >= self._effective_limit()

    def _effective_limit(self) -> int:
        """Return the iteration ceiling for the current conversation."""
        return (
            CODE_MODE_MAX_AGENTIC_ITERATIONS
            if self._code_mode_active()
            else MAX_AGENTIC_ITERATIONS
        )

    def _append_stop_instruction(
        self,
        messages: List[BaseMessage],
    ) -> List[BaseMessage]:
        """Append a stop-tools instruction to the last HumanMessage."""
        instruction = _STOP_TOOLS_INSTRUCTION.format(
            count=self._effective_limit(),
        )
        result = list(messages)
        for i in range(len(result) - 1, -1, -1):
            if isinstance(result[i], HumanMessage):
                content = str(result[i].content or "")
                result[i] = HumanMessage(content=content + instruction)
                return result
        result.append(HumanMessage(content=instruction))
        return result

    def force_final_response(
        self,
        messages: List[BaseMessage],
        generation_kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Keep tool results and generate one final text-only response.

        The final synthesis call receives the full message list — the
        tool-call AIMessages and their ToolMessages stay in context so
        the model can answer from what it actually learned.  When the
        stream produces no text, the project fallback hook is tried
        before the framework's generic apology.
        """
        self._owner.logger.info(
            "[AGENTIC GUARD] Forcing final response after %d cycles",
            self._effective_limit(),
        )
        final_prompt = self._append_stop_instruction(messages)
        try:
            response = self._owner._stream_model_response(
                final_prompt, generation_kwargs
            )
            if response is not None:
                content = (response.content or "").strip()
                if content:
                    return {
                        "messages": [
                            AIMessage(content=content, tool_calls=[])
                        ],
                        "workflow_continuation": False,
                        "loop_count": 0,
                    }
        except Exception as exc:
            self._owner.logger.error(
                "[AGENTIC GUARD] Final response failed: %s", exc
            )
        fallback = self._project_fallback(messages)
        if not fallback:
            fallback = _IN_CHARACTER_FALLBACK
        return {
            "messages": [AIMessage(
                content=fallback, tool_calls=[]
            )],
            "workflow_continuation": False,
            "loop_count": 0,
        }

    def _project_fallback(self, messages: List[BaseMessage]) -> str:
        """Return a project-specific fallback line when one is importable.

        Mirrors ``generation_response_support._try_project_fallback`` so
        UwUchat deployments get their in-character line and other
        deployments keep the framework default.
        """
        try:
            import importlib
            import os

            project = os.environ.get("AIRUNNER_PROJECT", "")
            if not project:
                from airunner_services.conf import settings

                project = getattr(settings, "AIRUNNER_PROJECT", "") or ""
            if not project:
                return ""
            mod = importlib.import_module(
                f"projects.{project}.server.fallback_response"
            )
            func = getattr(mod, "uwuchat_fallback_response", None)
            if func is None:
                func = getattr(mod, "headlesscode_fallback_response", None)
            if func is None:
                return ""
            return func(self._executed_tool_names(messages))
        except ImportError:
            return ""
        except Exception:
            self._owner.logger.warning(
                "Project fallback response raised an exception",
                exc_info=True,
            )
            return ""

    @staticmethod
    def _executed_tool_names(messages: List[BaseMessage]) -> List[str]:
        """Return the deduplicated tool names invoked in a message list."""
        names: List[str] = []
        for msg in messages:
            for call in getattr(msg, "tool_calls", None) or []:
                name = call.get("name")
                if name and name not in names:
                    names.append(name)
        return names
