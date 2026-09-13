"""Forced-tool execution policy for workflow tool runs."""

from __future__ import annotations

import uuid
from typing import Any, TYPE_CHECKING

from langchain_core.messages import AIMessage, ToolMessage

if TYPE_CHECKING:
    from airunner_services.llm.workflow_manager import WorkflowState

# Tools that are always allowed even when a force-tool is active.
# These are status-only / state-reporting tools with no side effects
# that could interfere with any workflow.
_ALWAYS_ALLOWED: frozenset[str] = frozenset(
    {
        "update_mood",
        "record_knowledge",
        "record_character_fact",
        "record_user_fact",
    }
)

# Tools whose execution must be followed by a forced check_grounding
# call before the model is allowed to emit free-text.  Matches the
# set in node_knowledge_gate.py:_SEARCH_TOOL_NAMES.
_GROUNDING_FORCED_TOOLS: frozenset[str] = frozenset(
    {
        "get_topic_brief",
        "search_news",
        "scrape_website",
        "search_fastsearch",
        "search_fastsearch_news",
        "search_web",
        "get_daily_newspaper",
    }
)


class ForcedToolExecutionPolicy:
    """Apply forced-tool constraints before and after ToolNode execution."""

    def __init__(self, owner: Any):
        self._owner = owner

    def prepare(
        self,
        state: "WorkflowState",
        tool_calls: list[dict],
    ) -> tuple["WorkflowState", list[dict], "WorkflowState | None"]:
        """Return the execution plan for the current forced-tool state."""
        force_tool = getattr(self._owner, "_force_tool", None)
        if not force_tool:
            return state, tool_calls, None

        first_tool = tool_calls[0].get("name") if tool_calls else None
        if first_tool != force_tool:
            # Status-only tools like update_mood are always safe to run.
            if first_tool in _ALWAYS_ALLOWED:
                return state, tool_calls, None
            return (
                state,
                tool_calls,
                self._build_violation_state(
                    tool_calls,
                    first_tool,
                    force_tool,
                ),
            )
        if len(tool_calls) == 1:
            return state, tool_calls, None

        # Discard parallel calls that aren't always-allowed.
        kept = [tool_calls[0]]
        for tool_call in tool_calls[1:]:
            name = tool_call.get("name")
            if name and name in _ALWAYS_ALLOWED:
                kept.append(tool_call)
            else:
                self._owner.logger.warning(
                    "Force tool active: discarding parallel call '%s'",
                    name,
                )
        if len(kept) == len(tool_calls):
            return state, tool_calls, None

        messages = list(state["messages"])
        last_message = messages[-1]
        messages[-1] = AIMessage(
            content=last_message.content,
            tool_calls=kept,
        )
        return {**state, "messages": messages}, kept, None

    def complete(
        self,
        tool_calls: list[dict],
        result_state: dict | None = None,
    ) -> None:
        """Apply post-execution force-tool cleanup and rebinding rules.

        Args:
            tool_calls: The tool call requests the model made.
            result_state: Optional ToolNode output state whose
                ``messages`` list contains ``ToolMessage`` results.
                When provided and the executed tool returned an error,
                grounding is NOT forced — the model must be free to
                retry or switch categories.
        """
        executed_tool = (
            tool_calls[0].get("name") if tool_calls else None
        )
        force_tool = getattr(self._owner, "_force_tool", None)

        # ── grounding forcing: after any search tool, force
        #    check_grounding before the model can emit free text.
        #    Skip when the tool result was an error — grounding
        #    against a failed call is meaningless. ──
        if (
            not force_tool
            and executed_tool
            and executed_tool in _GROUNDING_FORCED_TOOLS
            and not self._tool_call_errored(tool_calls, result_state)
        ):
            self._owner.logger.info(
                "Grounding: '%s' done, enforcing check_grounding",
                executed_tool,
            )
            self._owner._force_tool = "check_grounding"
            self._owner._tool_choice = {
                "type": "function",
                "function": {"name": "check_grounding"},
            }
            self._ensure_forced_tool_available("check_grounding")
            if hasattr(self._owner, "_bind_tools_to_model"):
                self._owner._bind_tools_to_model()
            return

        if not force_tool:
            return

        if executed_tool != force_tool:
            return

        # ── check_grounding was forced after a search tool;
        #    only clear the force if real claims were submitted ──
        if executed_tool == "check_grounding":
            if self._grounding_has_real_claims(tool_calls):
                self._owner.logger.info(
                    "Clearing force_tool '%s' after valid "
                    "grounding check",
                    force_tool,
                )
                self._owner._force_tool = None
                self._owner._tool_choice = None
                if hasattr(self._owner, "_unbind_tools_from_model"):
                    self._owner._unbind_tools_from_model()
                return
            self._owner.logger.warning(
                "check_grounding called with no verifiable claims "
                "— force remains active"
            )
            return

        next_tool = self._owner._get_next_workflow_tool(executed_tool)
        if next_tool:
            self._owner.logger.info(
                "Workflow sequence: '%s' done, now enforcing '%s'",
                executed_tool,
                next_tool,
            )
            self._owner._force_tool = next_tool
            self._owner._tool_choice = {
                "type": "function",
                "function": {"name": next_tool},
            }
            self._ensure_forced_tool_available(next_tool)
            if hasattr(self._owner, "_bind_tools_to_model"):
                self._owner._bind_tools_to_model()
            return

        self._owner.logger.info(
            "Clearing force_tool '%s' after successful execution",
            force_tool,
        )
        self._owner._force_tool = None
        self._owner._tool_choice = None
        if hasattr(self._owner, "_unbind_tools_from_model"):
            self._owner._unbind_tools_from_model()

    def _ensure_forced_tool_available(self, tool_name: str) -> None:
        """Ensure `tool_name` is present in the owner's bound tool set.

        Forcing `tool_choice` to name a tool that isn't part of the
        schema actually sent to the provider causes the provider to
        reject the request (e.g. "Tool 'X' not found in provided
        tools"). Grounding/workflow-sequence forcing can name a tool
        whose category wasn't part of the current request's filtered
        tool selection, so it must be appended explicitly before
        rebinding. Mirrors the lookup already used by
        `ToolFilteringMixin._resolve_forced_tool_for_empty_plan`.
        """
        tools = getattr(self._owner, "_tools", None)
        if tools is None:
            return
        for existing in tools:
            name = getattr(
                existing, "name", getattr(existing, "__name__", None)
            )
            if name == tool_name:
                return
        tool_manager = getattr(self._owner, "_tool_manager", None)
        if not tool_manager:
            return
        tool = tool_manager._get_tool_by_name(tool_name)
        if tool is None:
            self._owner.logger.warning(
                "Forced tool '%s' not found in tool manager - cannot "
                "add it to the bound tool set",
                tool_name,
            )
            return
        self._owner._tools = list(tools) + [tool]

    @staticmethod
    def _grounding_has_real_claims(tool_calls: list[dict]) -> bool:
        """Return True if check_grounding was called with >=1 verifiable
        claim.

        A "verifiable" claim is a non-empty string of at least 12
        characters — the same threshold used by the claim-matching
        logic in _claim_matching.py.  Claims shorter than this or empty
        strings are not checked, so passing only those is effectively
        a bypass.
        """
        if not tool_calls:
            return False
        args = tool_calls[0].get("args", {}) or {}
        claims: list[str] = args.get("claims", []) or []
        return any(
            isinstance(c, str) and len(c.strip()) >= 12
            for c in claims
        )

    @staticmethod
    def _tool_call_errored(
        tool_calls: list[dict],
        result_state: dict | None,
    ) -> bool:
        """Return True when the first tool call's result is an error.

        Matches the convention used by
        :meth:`node_post_tool_instructions_helper._error_instruction`:
        content starting with ``"ERROR:"`` or ``"Error:"``.
        """
        if not result_state or not tool_calls:
            return False
        tool_call_id = tool_calls[0].get("id")
        if not tool_call_id:
            return False
        messages = result_state.get("messages", [])
        for msg in messages:
            if getattr(msg, "tool_call_id", None) != tool_call_id:
                continue
            content = str(getattr(msg, "content", ""))
            return content.startswith("ERROR:") or content.startswith(
                "Error:"
            )
        return False

    def _build_violation_state(
        self,
        tool_calls: list[dict],
        called_tool: str | None,
        force_tool: str,
    ) -> "WorkflowState":
        """Return an error tool result when the wrong tool was called."""
        self._owner.logger.error(
            "Force tool violation: model called '%s' but must call '%s' "
            "first",
            called_tool,
            force_tool,
        )
        error_msg = (
            f"ERROR: You must call '{force_tool}' first.\n\n"
            f"You tried to call '{called_tool}', but the workflow "
            f"requires calling '{force_tool}' before any other tool.\n\n"
            f"Call {force_tool} NOW."
        )
        tool_call_id = tool_calls[0].get("id", str(uuid.uuid4()))
        error_result = ToolMessage(
            content=error_msg,
            tool_call_id=tool_call_id,
            name=called_tool,
        )
        return {"messages": [error_result]}
