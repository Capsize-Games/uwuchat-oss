"""Tool selection logic for ToolManager."""

from __future__ import annotations

from typing import Callable, List

from airunner_services.contract_enums import LLMActionType

# Tools whose information is already injected into the per-turn
# context block — exposing them to the model just wastes expensive
# DIALOGUE calls on redundant getter invocations.
_REDUNDANT_WITH_PER_TURN_CONTEXT = frozenset({
    "get_current_datetime",
    "get_current_date_context",
})


class ToolManagerSelectionMixin:
    """Action-based tool selection methods for ToolManager."""

    logger: any
    _get_tool_by_name: any
    _wrap_tool_with_dependencies: any
    get_all_tools: any

    def get_tools_for_action(self, action: any) -> List[Callable]:
        """Return the tools appropriate for one action type."""
        tools = self._get_tools_for_action_impl(action)
        return [
            t for t in tools
            if getattr(t, "name", None) not in _REDUNDANT_WITH_PER_TURN_CONTEXT
        ]

    def _get_tools_for_action_impl(self, action: any) -> List[Callable]:
        """Internal tool selection before redundant-tool filtering."""
        common = self._common_tools()
        if action == LLMActionType.CHAT:
            return common + self._action_tools(
                [
                    "clear_conversation",
                    "toggle_tts",
                    "search_news",
                    "get_my_weather",
                    "search_weather",
                ],
            )
        if action == LLMActionType.GENERATE_IMAGE:
            return common + self._action_tools(
                ["generate_image", "clear_canvas", "open_image"],
            )
        if action == LLMActionType.PERFORM_RAG_SEARCH:
            return common + self._rag_search_tools()
        if action == LLMActionType.APPLICATION_COMMAND:
            return self.get_all_tools()
        return common

    def _common_tools(self) -> List[Callable]:
        """Return tools that are common to all actions.

        Note: update_mood is intentionally excluded.  Mood updates are
        handled by the INTRA_SESSION_MOOD pipeline stage (background,
        every N turns).  Exposing update_mood as a tool causes the
        model to call it on every agentic loop cycle, wasting
        DIALOGUE calls until MAX_AGENTIC_ITERATIONS forces a final
        response.  See also: prompt_builder/mood.py.
        """
        result = []
        for name in [
            "recall_knowledge",
            "recall_character_facts",
        ]:
            tool = self._get_tool_by_name(name)
            if tool:
                result.append(tool)
        return result

    def _action_tools(self, names: list[str]) -> List[Callable]:
        """Return tools for the given name list."""
        result = []
        for name in names:
            tool = self._get_tool_by_name(name)
            if tool:
                result.append(tool)
        return result

    def _rag_search_tools(self) -> List[Callable]:
        """Return RAG-search-specific tools."""
        additional = []
        try:
            from airunner_services.llm.core.tool_registry import ToolRegistry

            for tool_info in ToolRegistry.all().values():
                name_lower = (tool_info.name or "").lower()
                cat_lower = str(getattr(tool_info, "category", "")).lower()
                if any(
                    kw in name_lower or kw in cat_lower
                    for kw in ("search", "rag", "knowledge")
                ):
                    wrapped = self._wrap_tool_with_dependencies(tool_info)
                    wrapped.name = tool_info.name
                    wrapped.description = tool_info.description
                    wrapped.return_direct = tool_info.return_direct
                    wrapped.category = getattr(tool_info, "category", None)
                    additional.append(wrapped)
        except Exception:
            self.logger.debug(
                "ToolRegistry unavailable for RAG search tools; falling back"
            )
        for name in [
            "rag_search",
            "search_web",
            "search_knowledge_base_documents",
        ]:
            tool = self._get_tool_by_name(name)
            if tool:
                additional.append(tool)
        return additional

    def get_tools_by_categories(
        self,
        categories: List,
        include_deferred: bool = False,
    ) -> List[Callable]:
        """Return tools filtered by the provided registry categories."""
        from airunner_services.llm.core.tool_registry import ToolRegistry

        if not categories:
            return []
        filtered = []
        seen = set()
        for category in categories:
            for tool_info in ToolRegistry.get_by_category(category):
                if tool_info.defer_loading and not include_deferred:
                    continue
                if tool_info.name not in seen:
                    seen.add(tool_info.name)
                    func = self._get_tool_by_name(tool_info.name)
                    if func:
                        filtered.append(func)
        self.logger.info(
            "Filtered to %d tools from categories: %s (deferred=%s)",
            len(filtered),
            [c.value for c in categories],
            include_deferred,
        )
        return filtered
