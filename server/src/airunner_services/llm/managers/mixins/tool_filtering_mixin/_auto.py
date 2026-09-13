"""Auto tool-category selection mixin.

Extracted from ``ToolFilteringMixin``.  Auto-selects tool categories
from the prompt using heuristic triggers, and emits tool-selection
status events.
"""

from __future__ import annotations

from typing import Optional

from airunner_services.llm.managers.mixins.tool_classification_mixin \
    import _is_terse
from airunner_services.llm.managers.mixins.tool_filtering_mixin._helpers import (
    _reconcile_search_research,
)
from airunner_services.llm_workflow_events import (
    resolve_llm_workflow_event_sink,
)


def _project_code_mode_active(owner) -> bool:
    """Return True when the active project's code-mode toggle is on for
    *owner*'s current conversation.

    Guarded import of ``projects.<active>.server.code_mode_service`` —
    absent module or any import error returns False (no-op for any
    non-UwUchat deployment). Same pattern as
    request_handling_mixin/_stages.py's tool-execution-stage import.
    """
    try:
        import importlib
        import os

        project = os.environ.get("AIRUNNER_PROJECT", "")
        if not project:
            from airunner_services.conf import settings

            project = getattr(settings, "AIRUNNER_PROJECT", "") or ""
        if not project:
            return False
        mod = importlib.import_module(
            f"projects.{project}.server.code_mode_service"
        )
        func = getattr(mod, "code_mode_active_for_owner", None)
        if func is None:
            return False
        return bool(func(owner))
    except Exception:
        return False


class ToolFilterAutoMixin:
    """Auto-select tool categories from the prompt."""

    def _auto_select_tool_categories(
        self,
        prompt: str,
        force_tool: Optional[str] = None,
        allow_thinking: bool = True,
        request_id: Optional[str] = None,
    ) -> tuple[list[str], Optional[str]]:
        """Return auto-selected categories and any forced tool override."""
        tool_status_id = (
            f"tool_classification_{request_id}"
            if request_id
            else "tool_classification"
        )
        self._emit_tool_selection_status(
            tool_status_id,
            prompt,
            "starting",
            "Analyzing prompt to select tools...",
            request_id,
        )

        direct_categories, direct_force_tool = self._detect_simple_tool_route(
            prompt
        )
        if force_tool is None and direct_force_tool:
            force_tool = direct_force_tool

        if direct_categories is not None:
            selected_categories = direct_categories
            self.logger.info(
                "Auto mode: matched direct system tool route %s for prompt %r",
                force_tool,
                prompt[:100],
            )
        elif self._is_simple_greeting_prompt(prompt):
            self.logger.info("Auto mode: greeting detected, disabling tools")
            selected_categories = []
        elif self._is_simple_no_tool_prompt(prompt):
            self.logger.info(
                "Auto mode: simple conversational prompt detected, "
                "disabling tools"
            )
            selected_categories = []
        elif self._is_constrained_reply_prompt(prompt):
            self.logger.info(
                "Auto mode: constrained reply prompt detected, "
                "disabling tools"
            )
            selected_categories = []
        elif self._has_weather_trigger_prompt(prompt):
            self.logger.info(
                "Auto mode: weather intent detected, "
                "enabling system category"
            )
            selected_categories = ["system"]
        elif self._has_search_trigger_prompt(prompt):
            categories = ["search"]
            if self._has_recall_trigger_prompt(prompt):
                # A generic search word (e.g. "find") can co-occur with a
                # recall-specific phrase (e.g. "from our conversations").
                # Bind both categories instead of letting the generic word
                # win outright and silently dropping recall tools.
                categories.append("recall")
            self.logger.info(
                "Auto mode: search intent detected, enabling categories %s",
                categories,
            )
            selected_categories = categories
        elif self._is_image_generation_prompt(prompt):
            self.logger.info(
                "Auto mode: image generation intent detected, "
                "enabling image category"
            )
            selected_categories = ["image"]
        elif self._has_calendar_trigger_prompt(prompt):
            self.logger.info(
                "Auto mode: calendar intent detected, "
                "enabling system category"
            )
            selected_categories = ["system"]
        elif self._has_math_trigger_prompt(prompt):
            self.logger.info(
                "Auto mode: math intent detected, enabling math category"
            )
            selected_categories = ["math"]
        elif self._has_recall_trigger_prompt(prompt):
            self.logger.info(
                "Auto mode: recall intent detected, enabling recall category"
            )
            selected_categories = ["recall"]
        elif (
            _is_terse(prompt) or self._is_retry_phrase(prompt)
        ) and self._recent_lookup_category(self):
            category = self._recent_lookup_category(self)
            self.logger.info(
                "Auto mode: retry/continuation follow-up after "
                "recent %s lookup, re-enabling %s category",
                category, category,
            )
            selected_categories = [category]
        else:
            selected_categories = self._classify_prompt_for_tools(
                prompt,
                allow_thinking=allow_thinking,
            )

        # Code-mode hook: when the active project's code-mode toggle is on
        # for this conversation, always bind the CODE category so the inline
        # agent tools (execute_command, read_file, ...) are available to
        # DIALOGUE regardless of what the classifier picked — the classifier
        # biases toward "research" for prompts naming real orgs/platforms
        # (e.g. "github"). "code" is native-routed to DIALOGUE
        # (_NATIVE_ROUTING_CATEGORIES), so it stays out of the cheap stage.
        if _project_code_mode_active(self):
            if "code" not in selected_categories:
                selected_categories.append("code")
                self.logger.info(
                    "Auto mode: code mode active — added 'code' category"
                )

        selected_categories = _reconcile_search_research(
            selected_categories,
        )

        details = (
            "Selected: "
            f"{', '.join(selected_categories) if selected_categories else 'none'}"
        )
        if force_tool:
            details += f" | forced tool: {force_tool}"
        self._emit_tool_selection_status(
            tool_status_id,
            prompt,
            "completed",
            details,
            request_id,
        )
        return selected_categories, force_tool

    def _emit_tool_selection_status(
        self,
        tool_status_id: str,
        prompt: str,
        status: str,
        details: str,
        request_id: Optional[str],
    ) -> None:
        """Emit one tool-selection status event."""
        from datetime import datetime, timezone

        event_sink = resolve_llm_workflow_event_sink(self)
        event_sink.emit_tool_status(
            {
                "tool_id": tool_status_id,
                "tool_name": "tool_analyzer",
                "query": prompt[:100],
                "status": status,
                "details": details,
                "conversation_id": getattr(self, "_conversation_id", None),
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
