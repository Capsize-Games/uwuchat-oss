"""Request-time tooling preparation mixin.

Extracted from ``RequestHandlingMixin``.  Builds default tool
arguments from request search hints and applies per-request tool
filtering with system-prompt overrides.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from airunner_services.llm.managers.request_preparation import (
    extract_request_tool_defaults,
)


class RequestToolingMixin:
    """Tool filtering and defaulting for incoming LLM requests."""

    def _request_tool_defaults(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Build default tool arguments from request search hints."""
        request_data = data.get("request_data", {})
        if not isinstance(request_data, dict):
            return {}
        return extract_request_tool_defaults(request_data)

    def _prepare_request_tooling(
        self,
        data: Dict[str, Any],
        llm_request: Any,
        prompt_override: str | None = None,
    ) -> tuple[bool, List[str], Optional[str]]:
        """Apply per-request tool filtering and system prompt overrides."""
        tools_filtered = False
        selected_categories: List[str] = []
        system_prompt = None
        if llm_request:
            self.logger.info(
                "[LLM MANAGER DEBUG] llm_request.tool_categories=%s",
                llm_request.tool_categories,
            )
            if getattr(llm_request, "system_prompt", None):
                system_prompt = llm_request.system_prompt
                self.logger.info(
                    "Using custom system prompt from request: %s...",
                    system_prompt[:100],
                )

        prompt = prompt_override or data["request_data"]["prompt"]
        action = data["request_data"].get("action")

        if llm_request:
            selected_categories = getattr(llm_request, "tool_categories", None)
            allow_thinking = getattr(llm_request, "enable_thinking", None)
            if allow_thinking is None:
                allow_thinking = True
            # Treat empty list same as None: LLMRequest.tool_categories
            # defaults to [] via field(default_factory=list), so a fresh
            # request has an empty list rather than None.  Auto-select
            # must still kick in for those cases.
            auto_select = not selected_categories
            plan = self._build_tool_selection_plan(
                prompt=prompt,
                tool_categories=(
                    selected_categories if not auto_select else None
                ),
                action=action,
                force_tool=getattr(llm_request, "force_tool", None),
                allow_thinking=bool(allow_thinking),
                request_id=getattr(self, "_current_request_id", None),
                auto_select=auto_select,
            )
            llm_request.tool_categories = plan.selected_categories
            llm_request.force_tool = plan.force_tool
            self.logger.info(
                "[LLM MANAGER DEBUG] APPLYING TOOL PLAN with %s",
                plan.selected_categories,
            )
            self._apply_tool_selection_plan(plan)
            selected_categories = list(plan.selected_categories or [])
            tools_filtered = True
        else:
            self.logger.info(
                "[LLM MANAGER DEBUG] NOT APPLYING FILTER - tool_categories "
                "is None"
            )
            self.logger.info("No tool filtering - using all tools")

        return tools_filtered, selected_categories, system_prompt
