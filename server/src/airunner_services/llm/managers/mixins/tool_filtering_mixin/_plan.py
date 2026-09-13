"""Tool-selection plan construction mixin.

Extracted from ``ToolFilteringMixin``.  Builds the canonical
``ToolSelectionPlan`` for a request: all-tools/empty plans and the
main plan builder.  Auto-selection heuristics live in ``_auto`` and
normalization/forced-tool helpers in ``_normalize``.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

from airunner_services.llm.core.tool_registry import ToolCategory
from airunner_services.llm.managers.tool_selection_plan import (
    ToolSelectionPlan,
)

# Categories bound directly to the dialogue model; never routed
# through the cheap-stage tool-execution pre-pass.  ``code`` joins
# math/system so CODE-category tools (e.g. a headlesscode session
# launcher) execute inside DIALOGUE, which narrates their result —
# never in the cheap stage's bounded iteration loop.
_NATIVE_ROUTING_CATEGORIES = ("math", "system", "code")

# Knowledge-category tools that must never be bound to the DIALOGUE
# model during inline generation.  These are write/mutation tools;
# a cheap background extractor handles knowledge capture after each
# turn.  Read tools (recall_knowledge, recall_character_facts,
# read_knowledge_file, list_knowledge_files) are NOT in this set and
# remain bindable when the classifier selects "knowledge".
_KNOWLEDGE_WRITE_TOOL_NAMES: frozenset[str] = frozenset({
    "record_knowledge",
    "record_character_fact",
    "update_knowledge",
    "delete_knowledge",
})


class ToolFilterPlanMixin:
    """Build and normalize tool-selection plans."""

    CATEGORY_ALIASES = {
        "user_data": "knowledge",
        "agent": "system",
        "agents": "system",
        "memory": "knowledge",
    }

    def _build_tool_selection_plan(
        self,
        prompt: str,
        tool_categories: Optional[List[str]],
        action: Any = None,
        force_tool: Optional[str] = None,
        allow_thinking: bool = True,
        request_id: Optional[str] = None,
        auto_select: bool = False,
    ) -> ToolSelectionPlan:
        """Return the canonical tool-selection plan for one request."""
        selected_categories = None
        resolved_force_tool = force_tool
        if auto_select:
            selected_categories, resolved_force_tool = (
                self._auto_select_tool_categories(
                    prompt=prompt,
                    force_tool=force_tool,
                    allow_thinking=allow_thinking,
                    request_id=request_id,
                )
            )
        elif tool_categories is not None:
            selected_categories = list(tool_categories)

        if not self._workflow_manager or not self._tool_manager:
            self.logger.warning(
                "Cannot build tool plan - workflow_manager or tool_manager "
                "not initialized"
            )
            return ToolSelectionPlan(
                selected_categories=selected_categories,
                effective_categories=None,
                filtered_tools=None,
                force_tool=resolved_force_tool,
                keep_existing_tools=True,
            )

        if selected_categories is None:
            return self._build_all_tools_plan(action, resolved_force_tool)
        if len(selected_categories) == 0:
            return self._build_empty_tool_plan(
                prompt,
                resolved_force_tool,
            )

        effective_categories = self._normalize_tool_categories(
            selected_categories
        )
        if not effective_categories:
            self.logger.warning(
                "No valid tool categories specified - leaving tools "
                "unchanged"
            )
            return ToolSelectionPlan(
                selected_categories=selected_categories,
                effective_categories=[],
                filtered_tools=None,
                force_tool=resolved_force_tool,
                keep_existing_tools=True,
            )

        filtered_tools = self._tool_manager.get_tools_by_categories(
            [ToolCategory(category) for category in effective_categories],
            include_deferred=True,
        )
        # Exclude knowledge write tools from inline DIALOGUE binding.
        # Record/update/delete are handled by the cheap background
        # extractor; only read tools (recall_knowledge etc.) should
        # be bound when the classifier selects "knowledge".
        if "knowledge" in effective_categories:
            before = len(filtered_tools)
            filtered_tools = [
                t for t in filtered_tools
                if getattr(t, "name", "") not in _KNOWLEDGE_WRITE_TOOL_NAMES
            ]
            removed = before - len(filtered_tools)
            if removed:
                self.logger.info(
                    "Excluded %d knowledge write tool(s) from "
                    "DIALOGUE binding (handled by background "
                    "extractor)",
                    removed,
                )
        filtered_tools = self._restrict_to_forced_tool(
            filtered_tools,
            resolved_force_tool,
        )
        return ToolSelectionPlan(
            selected_categories=selected_categories,
            effective_categories=effective_categories,
            filtered_tools=filtered_tools,
            force_tool=resolved_force_tool,
            tool_choice=self._resolve_tool_choice(
                resolved_force_tool,
                action,
                effective_categories,
            ),
        )

    def _build_all_tools_plan(
        self,
        action: Any,
        force_tool: Optional[str],
    ) -> ToolSelectionPlan:
        """Return the plan that enables the full tool set."""
        self.logger.info("tool_categories=None - enabling all tools")
        disabled_categories = self._disabled_tool_categories()
        all_tools = [
            tool
            for tool in self._tool_manager.get_all_tools()
            if getattr(tool, "category", None) is None
            or getattr(tool.category, "value", None) not in disabled_categories
        ]
        return ToolSelectionPlan(
            selected_categories=None,
            effective_categories=None,
            filtered_tools=all_tools,
            force_tool=force_tool,
            tool_choice=self._resolve_tool_choice(force_tool, action, None),
            rebuild_workflow=True,
        )

    def _build_empty_tool_plan(
        self,
        prompt: str,
        force_tool: Optional[str],
    ) -> ToolSelectionPlan:
        """Return the plan for an explicit empty category selection."""
        disable_always = (
            os.environ.get("AIRUNNER_DISABLE_ALWAYS_TOOLS", "0") == "1"
        )
        if (
            disable_always
            or self._is_simple_greeting_prompt(prompt)
            or self._is_simple_no_tool_prompt(prompt)
        ):
            filtered = self._resolve_forced_tool_for_empty_plan(force_tool)
            self.logger.info(
                "tool_categories=[] - disabling tools for this request"
                + (
                    " (keeping force_tool=%s)" % force_tool
                    if force_tool
                    else ""
                )
            )
            return ToolSelectionPlan(
                selected_categories=[],
                effective_categories=[],
                filtered_tools=filtered,
                force_tool=force_tool,
                tool_choice=self._resolve_tool_choice(
                    force_tool, None, []
                ),
                rebuild_workflow=True,
            )

        auto_extract = getattr(
            getattr(self, "llm_settings", None), "auto_extract_knowledge", True
        )
        effective_categories = sorted(
            cat
            for cat in self.ALWAYS_INCLUDE_CATEGORIES
            if cat != "knowledge" or auto_extract
        )
        self.logger.info(
            "tool_categories=[] - including always-available categories: %s",
            effective_categories,
        )
        return ToolSelectionPlan(
            selected_categories=[],
            effective_categories=effective_categories,
            filtered_tools=self._tool_manager.get_tools_by_categories(
                [ToolCategory(category) for category in effective_categories],
                include_deferred=True,
            ),
            force_tool=force_tool,
            rebuild_workflow=True,
        )

