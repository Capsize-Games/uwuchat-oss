"""Category normalization and forced-tool helpers.

Extracted from ``ToolFilteringMixin``.  Normalizes category aliases,
applies disabled-category filtering, restricts tool sets to a forced
tool, and resolves the request-time ``tool_choice`` override.
"""

from __future__ import annotations

from typing import Any, List, Optional

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.core.tool_registry import ToolCategory


class ToolFilterNormalizeMixin:
    """Category normalization and forced-tool helpers."""

    def _resolve_forced_tool_for_empty_plan(
        self,
        force_tool: Optional[str],
    ) -> list[Any]:
        """Return the forced tool when building an empty tool plan.

        When a force_tool is active but the prompt qualifies as a simple
        greeting (no tools needed), we must still include the forced tool
        in the ToolNode so it can be executed.  Without this the LLM would
        generate a tool call that the ToolNode cannot find.
        """
        if not force_tool or not self._tool_manager:
            return []
        tool = self._tool_manager._get_tool_by_name(force_tool)
        if tool is None:
            self.logger.warning(
                "Force tool '%s' not found in tool manager for empty plan",
                force_tool,
            )
            return []
        self.logger.info(
            "Empty tool plan with force_tool='%s' — including it alone",
            force_tool,
        )
        return [tool]

    def _disabled_tool_categories(self) -> set[str]:
        """Return tool categories a project has opted out of entirely.

        Reads ``PIPELINE_CONFIG["TOOL_CATEGORIES"]["disabled"]`` from the
        active project's ``ai_pipeline.py`` (see ``pipeline_loader``).
        Empty for any project that doesn't define this key — this is a
        generic, project-agnostic hook, not UwUchat-specific logic.
        """
        # Deferred import: tests patch
        # ``tool_filtering_mixin.pipeline_config`` on the package module,
        # so resolve through the package namespace at call time.
        from airunner_services.llm.managers.mixins import tool_filtering_mixin
        disabled = tool_filtering_mixin.pipeline_config(
            "TOOL_CATEGORIES"
        ).get("disabled", [])
        return {str(c).lower() for c in disabled}

    def _normalize_tool_categories(
        self,
        tool_categories: List[str],
    ) -> list[str]:
        """Normalize aliases and add always-include categories."""
        effective_categories: list[str] = []
        seen_categories: set[str] = set()
        disabled_categories = self._disabled_tool_categories()
        for cat_name in tool_categories:
            category_name = self.CATEGORY_ALIASES.get(
                (cat_name or "").lower(),
                (cat_name or "").lower(),
            )
            try:
                category = ToolCategory(category_name)
            except ValueError:
                self.logger.warning(
                    "Unknown tool category: %s. Valid categories: %s. "
                    "Valid aliases: %s",
                    cat_name,
                    [item.value for item in ToolCategory],
                    sorted(self.CATEGORY_ALIASES),
                )
                continue
            if category.value in disabled_categories:
                continue
            if category.value not in seen_categories:
                effective_categories.append(category.value)
                seen_categories.add(category.value)

        auto_extract = getattr(
            getattr(self, "llm_settings", None), "auto_extract_knowledge", True
        )
        for always_cat in sorted(self.ALWAYS_INCLUDE_CATEGORIES):
            if always_cat == "knowledge" and not auto_extract:
                continue
            if always_cat not in seen_categories:
                effective_categories.append(always_cat)
                seen_categories.add(always_cat)
        return effective_categories

    def _restrict_to_forced_tool(
        self,
        filtered_tools: list[Any],
        force_tool: Optional[str],
    ) -> list[Any]:
        """Reduce the filtered tool set to one forced tool when requested."""
        if not force_tool:
            return filtered_tools

        forced_tools = [
            tool
            for tool in filtered_tools
            if getattr(tool, "name", getattr(tool, "__name__", None))
            == force_tool
        ]
        if forced_tools:
            self.logger.info(
                "[TOOL FILTER] Reduced filtered tools to forced tool: %s",
                force_tool,
            )
            return forced_tools

        # The forced tool's category wasn't part of this request's
        # selected categories (e.g. check_grounding is QA-category but
        # gets forced after a SEARCH tool runs). tool_choice will still
        # be pinned to force_tool by _resolve_tool_choice, so it MUST
        # be present in the tool schema sent to the provider or the
        # provider rejects the request with "Tool 'X' not found in
        # provided tools". Look it up directly rather than silently
        # returning a tool set that excludes it.
        tool = (
            self._tool_manager._get_tool_by_name(force_tool)
            if self._tool_manager
            else None
        )
        if tool is not None:
            self.logger.info(
                "[TOOL FILTER] Forced tool '%s' not in filtered set - "
                "adding it directly",
                force_tool,
            )
            return filtered_tools + [tool]

        self.logger.warning(
            "[TOOL FILTER] Forced tool '%s' was not found in filtered "
            "tool set or the tool manager",
            force_tool,
        )
        return filtered_tools

    def _resolve_tool_choice(
        self,
        force_tool: Optional[str],
        action: Any,
        tool_categories: Optional[List[str]],
    ) -> Any:
        """Return the request-time tool choice override."""
        supports_forced_choice = bool(
            getattr(self, "supports_function_calling", False)
        )
        if force_tool:
            self.logger.info("[TOOL FILTER] Forcing tool: %s", force_tool)
            return {
                "type": "function",
                "function": {"name": force_tool},
            }
        if (
            supports_forced_choice
            and action == LLMActionType.PERFORM_RAG_SEARCH
        ):
            return "any"
        if (
            supports_forced_choice
            and tool_categories
            and ("search" in tool_categories or "research" in tool_categories)
        ):
            return "any"
        if action == LLMActionType.CODE:
            self.logger.info(
                "[TOOL FILTER] CODE action uses generic fallback handling; "
                "leaving tool_choice unset"
            )
        return None
