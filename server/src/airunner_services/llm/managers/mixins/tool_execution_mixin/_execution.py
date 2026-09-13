"""ToolNode execution orchestration for ToolExecutionMixin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from airunner_services.llm.managers.mixins.tool_call_args import (
    coerce_non_string_tool_args,
)

if TYPE_CHECKING:  # pragma: no cover - import-time type-only block
    from airunner_services.llm.workflow_manager import WorkflowState


def _record_search_tools_discoveries(
    owner, tool_calls: list, result_state: dict,
) -> None:
    """Parse search_tools results and record discovered tool names.

    Called after ToolNode.invoke() completes.  When the model called
    ``search_tools``, its result is a JSON string with a ``tools``
    array of schema dicts, each with a ``name`` key.  These names are
    added to ``owner._discovered_tools`` so that
    :meth:`_ensure_tools_loaded` can safely load them on subsequent
    iterations.
    """
    import json

    from langchain_core.messages import ToolMessage

    messages = result_state.get("messages", [])
    for tc in tool_calls:
        if tc.get("name") != "search_tools":
            continue
        tc_id = tc.get("id")
        if not tc_id:
            continue
        for msg in messages:
            if (
                isinstance(msg, ToolMessage)
                and getattr(msg, "tool_call_id", None) == tc_id
            ):
                try:
                    parsed = json.loads(str(msg.content))
                    for entry in parsed.get("tools", []) or []:
                        name = entry.get("name")
                        if name:
                            owner._discovered_tools.add(name)
                except (json.JSONDecodeError, TypeError):
                    continue


class ToolExecutionNodeMixin:
    """Run the ToolNode with status tracking and duplicate interception."""

    def _execute_tools_with_status(
        self, state: WorkflowState
    ) -> WorkflowState:
        """Custom tool execution node that emits status signals.

        This wraps the standard ToolNode behavior but adds real-time status
        updates that can be displayed in the UI.

        NOTE: Validation removed - bind_tools() ensures the model only receives
        valid tool schemas. Invalid calls should not occur with proper binding.

        Args:
            state: Workflow state containing messages

        Returns:
            Updated workflow state with tool results
        """
        self._ensure_runtime_compat()
        from langgraph.prebuilt import ToolNode

        # Get the last AIMessage which contains tool_calls
        messages = state["messages"]
        last_message = messages[-1] if messages else None

        if not last_message or not hasattr(last_message, "tool_calls"):
            # No tool calls to execute, just pass through
            return state

        tool_calls = last_message.tool_calls or []
        if not tool_calls:
            return state

        policy = self._get_forced_tool_policy()
        state, tool_calls, blocked_state = policy.prepare(state, tool_calls)
        if blocked_state is not None:
            return blocked_state

        # Drop tool calls with empty name or missing id (model generation bug)
        valid_tool_calls = [
            tc for tc in tool_calls
            if tc.get("name") and tc.get("id") is not None
        ]
        if len(valid_tool_calls) < len(tool_calls):
            dropped = [
                tc.get("name") or "<empty>" for tc in tool_calls
                if tc not in valid_tool_calls
            ]
            self.logger.warning(
                "Dropping %d invalid tool call(s): %s",
                len(tool_calls) - len(valid_tool_calls),
                dropped,
            )
            if not valid_tool_calls:
                return state
            curr_msgs = state["messages"]
            rebuilt = curr_msgs[-1].model_copy(
                update={"tool_calls": valid_tool_calls}
            )
            state = {
                **state,
                "messages": list(curr_msgs[:-1]) + [rebuilt],
            }
            tool_calls = valid_tool_calls

        # Ensure deferred tools discovered via search_tools are available
        self._ensure_tools_loaded(tool_calls, state)

        # Emit "starting" status for each tool
        self._emit_starting_status(tool_calls)

        # Pre-scan for switch_tool_category calls: if the model is
        # following the orchestration recovery flow (switch + target
        # tool in the same AIMessage batch), rebind tools BEFORE
        # building ToolNode so the target tool validates against the
        # updated tool set instead of being rejected.
        self._prebind_for_pending_category_switch(tool_calls)

        # Intercept duplicate single-call tools BEFORE ToolNode so
        # they produce synthetic ToolMessages instead of being
        # physically removed from self._tools.  This keeps the
        # tools array stable for prompt caching.
        active_calls, synthetic_results = (
            self._intercept_single_call_duplicates(tool_calls)
        )

        # Rebuild state with only active_calls so ToolNode never sees
        # the duplicate requests.  Mirror the existing pattern at
        # lines 249-274 for dropping invalid tool calls.
        if len(active_calls) < len(tool_calls):
            curr_msgs = state["messages"]
            rebuilt = curr_msgs[-1].model_copy(
                update={"tool_calls": active_calls}
            )
            state = {
                **state,
                "messages": list(curr_msgs[:-1]) + [rebuilt],
            }
            tool_calls = active_calls

        # If every call was intercepted (all duplicates), skip
        # ToolNode entirely.  Synthetic ToolMessages are injected
        # after this block.
        if active_calls:
            # Local models emit dict/list args for string params; coerce
            # them to JSON strings so ToolNode validation passes.
            active_calls = coerce_non_string_tool_args(active_calls)

            # Repopulate the grounding-sources ContextVar from graph
            # state before ToolNode runs so check_grounding (which
            # reads the ContextVar) sees sources stashed by prior
            # graph steps even across any internal context boundaries
            # within LangGraph's execution model.
            self._refresh_grounding_cache_from_state(state)

            # Sanitize tool functions to ensure docstrings exist before
            # wrapping.  Must run AFTER prebind so freshly-rebound tools
            # pass through sanitization.
            self._sanitize_tool_functions()
            tool_node = ToolNode(self._tools)
            result_state = tool_node.invoke(state)
        else:
            result_state = state

        # Restore PII placeholders in ToolMessage results before they
        # are persisted/returned: the model's NEXT iteration reads these
        # results as input, and _mask_prompt re-masks on egress, so a
        # placeholder that survives here (e.g. a read_file of a file
        # containing an email/password) would be fed back to the model
        # masked — the model cannot act on content it only sees as
        # "[EMAIL_1]"-style tokens.  This closes the loop: mask on the
        # way out, restore on the way back in.  Invoked via the class
        # so a mock owner in tests (which lacks the method) falls back
        # to a no-op instead of resolving to an auto-created mock that
        # would replace the real result state.
        restore = getattr(
            ToolExecutionNodeMixin, "_restore_tool_result_pii", None,
        )
        if restore is not None:
            result_state = restore(self, result_state)

        # If search_tools ran, record which deferred tools it surfaced
        # so _ensure_tools_loaded can safely load them on the next
        # iteration without trusting hallucinated tool names.
        _record_search_tools_discoveries(
            self, tool_calls, result_state,
        )

        # Restore current_mood state that update_mood previously set via
        # Command(update=...). LangGraph >=1.0.10 requires every Command to
        # carry a ToolMessage in update.messages, which update_mood cannot
        # provide without the tool_call_id.  The tool now stores the payload
        # in a ContextVar instead.
        if "update_mood" in self._executed_tools:
            self._maybe_restore_mood_state(result_state)

        # Inject synthetic ToolMessages for intercepted single-call
        # duplicates so the model still sees a result for each tool
        # call it made — the tools just don't re-execute.
        if synthetic_results:
            from langchain_core.messages import ToolMessage
            messages = list(result_state.get("messages", []))
            for call_id, text in synthetic_results.items():
                messages.append(
                    ToolMessage(content=text, tool_call_id=call_id)
                )
            result_state = {**result_state, "messages": messages}

        # Extract tool results and emit "completed" status
        self._emit_completed_status(result_state, tool_calls)

        # Stash search-tool results into the grounding cache so
        # check_grounding can access them when forced next.
        self._stash_grounding_sources(tool_calls, result_state)

        policy.complete(tool_calls, result_state)

        # NOTE: _deduplicate_executed_tools (physical tool removal +
        # rebind) is REMOVED.  Duplicate single-call tools are now
        # intercepted BEFORE ToolNode (see _intercept_single_call_duplicates
        # above), producing synthetic ToolMessages without mutating
        # self._tools.  This keeps the tools array stable across the
        # entire turn for prompt caching.

        # Handle category switch: if the model called
        # switch_tool_category successfully, rebind the model's tools
        # to the requested category for the next model turn.
        self._handle_category_switch(tool_calls, result_state)

        # Update LRU tracking for cross-turn eviction.
        self._record_tool_usage(tool_calls)

        return result_state

    def _restore_tool_result_pii(
        self, state: WorkflowState,
    ) -> WorkflowState:
        """Restore PII placeholders in ToolMessage results.

        ToolNode returns ToolMessages whose content may contain PII
        placeholders (masked on the prior egress by ``_mask_prompt``,
        which masks the full prompt — including the messages the model
        produced as tool calls and the file content returned by
        ``read_file``/``execute_command``).  Those results are fed back
        to the model on the next iteration, so a placeholder that is not
        restored here would be re-masked and the model would act on
        ``[EMAIL_1]``-style tokens instead of the real content.

        Returns a shallow-copied state with ToolMessage contents
        restored via the owner's PII vault; the original state is not
        mutated.
        """
        from airunner_services.llm.pii.vault import PIIVault

        vault = getattr(self, "_pii_vault", None)
        if not isinstance(vault, PIIVault):
            return state
        messages = list(state.get("messages", []))
        restored = False
        for i, msg in enumerate(messages):
            if msg.__class__.__name__ != "ToolMessage":
                continue
            content = getattr(msg, "content", None)
            if not isinstance(content, str) or not content.strip():
                continue
            from airunner_services.llm.pii.restorer import (
                restore_text,
            )
            fixed = restore_text(content, vault)
            if fixed != content:
                messages[i] = msg.model_copy(update={"content": fixed})
                restored = True
        if not restored:
            return state
        return {**state, "messages": messages}
