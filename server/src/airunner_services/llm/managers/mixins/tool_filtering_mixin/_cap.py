"""Cross-turn tool binding with LRU cap.

Extracted from ``ToolFilteringMixin``.  Appends new tools to the
existing bound set (never replacing), enforcing an LRU cap so tool
state does not grow unboundedly across turns.
"""

from __future__ import annotations

from typing import Any, List, Optional

from airunner_services.llm.managers.tool_selection_plan import (
    ToolSelectionPlan,
)


class ToolFilterApplyMixin:
    """Apply tool-selection plans with cross-turn LRU capping."""

    # Maximum bound tools across a conversation before LRU eviction
    # kicks in.  Post-Part-A, typical per-turn binding is 8-12 tools
    # (5-6 research + 3-4 from other categories + always-included set),
    # so a cap of 30 allows 2-3 turns of topic drift before pruning.
    _CROSS_TURN_TOOL_CAP: int = 30

    # Tools that must never be evicted regardless of the cap —
    # search_tools is the discovery mechanism, list_available_tools is
    # the always-available inventory, and update_mood is required for
    # correct in-character behavior on every turn.
    _ALWAYS_KEEP_TOOLS: frozenset[str] = frozenset({
        "search_tools",
        "list_available_tools",
        "update_mood",
    })

    def _append_tools_with_cap(
        self,
        new_tools: list,
        tool_choice=None,
    ) -> None:
        """Append *new_tools* to the existing bound set with a cap.

        Tools already present are not duplicated.  When appending would
        exceed ``_CROSS_TURN_TOOL_CAP``, the least-recently-used tools
        (by turn of last invocation) are evicted first.  Tools in
        ``_ALWAYS_KEEP_TOOLS`` are never evicted.

        Call ``_initialize_model`` after this to rebind the model.
        """
        if not self._workflow_manager:
            return

        # Reset tool state when the conversation changes.  The same
        # WorkflowManager instance is reused across conversations
        # (set_conversation_id swaps the checkpointer but not the
        # tools), so without this reset, append-only tool state
        # leaks across entirely unrelated conversations.
        conv_id = getattr(
            self._workflow_manager, "_conversation_id", None,
        )
        if not hasattr(self, "_tool_state_conversation_id"):
            self._tool_state_conversation_id: int | None = None
        if conv_id != self._tool_state_conversation_id:
            self._tool_state_conversation_id = conv_id
            self._tool_last_used: dict[str, int] = {}
            self._current_turn = 0
            self._workflow_manager._tools = []
            self.logger.info(
                "[TOOL RESET] New conversation %s — tool state cleared",
                conv_id,
            )

        existing = {
            getattr(t, "name", getattr(t, "__name__", None))
            for t in self._workflow_manager._tools
        }

        # Track tool usage for LRU eviction.  _tool_last_used maps
        # tool name → turn number; _current_turn increments each turn.
        if not hasattr(self, "_tool_last_used"):
            self._tool_last_used: dict[str, int] = {}
        if not hasattr(self, "_current_turn"):
            self._current_turn = 0
        self._current_turn += 1
        turn = self._current_turn

        added = 0
        for tool in new_tools:
            name = getattr(tool, "name", getattr(tool, "__name__", None))
            if not name or name in existing:
                continue
            existing.add(name)
            self._workflow_manager._tools.append(tool)
            self._tool_last_used[name] = turn
            added += 1

        # Cap enforcement: evict least-recently-used tools.
        total = len(self._workflow_manager._tools)
        cap = self._CROSS_TURN_TOOL_CAP
        if total > cap:
            # Sort by last-used turn (oldest first), skip always-keep
            scored = [
                (self._tool_last_used.get(
                    getattr(t, "name", getattr(t, "__name__", "")), 0,
                ), t)
                for t in self._workflow_manager._tools
                if getattr(t, "name", getattr(t, "__name__", ""))
                not in self._ALWAYS_KEEP_TOOLS
            ]
            scored.sort(key=lambda x: x[0])
            to_remove = total - cap
            removed_names: list[str] = []
            for _, tool in scored[:to_remove]:
                name = getattr(tool, "name", getattr(tool, "__name__", ""))
                removed_names.append(name)
                self._workflow_manager._tools.remove(tool)

            if removed_names:
                self.logger.info(
                    "[TOOL CAP] Evicted %d LRU tools: %s "
                    "(%d → %d total)",
                    len(removed_names),
                    removed_names,
                    total,
                    len(self._workflow_manager._tools),
                )

        if added > 0:
            self.logger.info(
                "[TOOL APPEND] Added %d new tools (total: %d, "
                "categories=%s)",
                added,
                len(self._workflow_manager._tools),
                getattr(
                    getattr(self, "llm_request", None),
                    "tool_categories", None,
                ),
            )

        if tool_choice is not None:
            self._workflow_manager._tool_choice = tool_choice
        self._workflow_manager._initialize_model()

    def _apply_tool_selection_plan(
        self,
        plan: ToolSelectionPlan,
    ) -> None:
        """Apply a prepared tool-selection plan to the workflow manager.

        New tools are APPENDED to the existing bound set (never replace),
        with an LRU cap to prevent unbounded growth across turns.  This
        keeps the tools array stable turn-to-turn so that Anthropic's
        prompt-caching (tools render first) can actually hit the cache.
        """
        if not self._workflow_manager:
            return
        if plan.keep_existing_tools or plan.filtered_tools is None:
            self.logger.info(
                "[TOOL FILTER] Leaving existing workflow tools unchanged"
            )
            return

        filtered_names = [
            getattr(tool, "name", getattr(tool, "__name__", str(tool)))
            for tool in plan.filtered_tools
        ]
        self.logger.info(
            "[TOOL FILTER] Appending plan categories=%s effective=%s "
            "tools=%s",
            plan.selected_categories,
            plan.effective_categories,
            filtered_names,
        )

        self._append_tools_with_cap(
            plan.filtered_tools,
            tool_choice=plan.tool_choice,
        )
        if plan.rebuild_workflow:
            self._workflow_manager._build_and_compile_workflow()

    def _apply_tool_filter(
        self,
        tool_categories: List[str],
        action=None,
        force_tool: Optional[str] = None,
    ) -> None:
        """Apply a tool category filter to the active workflow."""
        plan = self._build_tool_selection_plan(
            prompt=getattr(getattr(self, "llm_request", None), "prompt", ""),
            tool_categories=tool_categories,
            action=action,
            force_tool=force_tool,
        )
        self._apply_tool_selection_plan(plan)

    def _restore_all_tools(self) -> None:
        """Restore all tools to the workflow after a filtered request."""
        if self._workflow_manager and self._tool_manager:
            all_tools = self._tool_manager.get_all_tools()
            self._workflow_manager.update_tools(all_tools)
