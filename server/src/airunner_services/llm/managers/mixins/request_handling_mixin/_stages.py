"""Request-time execution-stage mixin.

Extracted from ``RequestHandlingMixin``.  Runs the cheap-model
tool-execution stage, safety pre-flight, and stores cheap-stage hints
for per-turn injection.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from airunner_services.llm.managers.mixins.tool_filtering_mixin import (
    _NATIVE_ROUTING_CATEGORIES,
)


class RequestStageMixin:
    """Pre-flight and cheap tool-execution stage orchestration."""

    def _maybe_run_tool_execution_stage(
        self,
        prompt: str,
        selected_categories: list[str],
        llm_request: Any,
    ) -> dict | None:
        """Run the cheap-model tool-execution stage when applicable.

        `math` and `system` are always bound directly to the dialogue
        model and never reach this stage. Only runs when a
        TOOL_EXECUTION model is available and the remaining selected
        categories include cheap-stage categories (research, search).
        Tool results are persisted to the conversation so the DIALOGUE
        model sees them as context.
        """
        native_set = set(_NATIVE_ROUTING_CATEGORIES)
        remaining = [
            c for c in selected_categories if c not in native_set
        ]
        if not remaining:
            self.logger.info(
                "TOOL_EXECUTION cheap stage skipped: all selected "
                "categories %s are native-routed to the dialogue "
                "model.",
                selected_categories,
            )
            return None
        self.logger.info(
            "TOOL_EXECUTION cheap stage running for %s only; %s "
            "native-routed directly to the dialogue model.",
            remaining,
            [c for c in selected_categories if c in native_set],
        )
        selected_categories = remaining

        specialized = getattr(self, "_specialized_chat_models", {})
        cheap_model = specialized.get("TOOL_EXECUTION")
        if cheap_model is None:
            self.logger.warning(
                "TOOL_EXECUTION cheap stage skipped: "
                "no TOOL_EXECUTION model in _specialized_chat_models "
                "(available keys: %s). All tool calls will run on the "
                "expensive DIALOGUE model.",
                list(specialized.keys()),
            )
            return None

        try:
            import importlib
            import os

            project = os.environ.get("AIRUNNER_PROJECT", "")
            if not project:
                from airunner_services.conf import settings

                project = getattr(settings, "AIRUNNER_PROJECT", "") or ""
            if not project:
                return None
            mod = importlib.import_module(
                f"projects.{project}.server.tool_execution_stage"
            )
            run_tool_execution_stage = mod.run_tool_execution_stage
        except ImportError:
            self.logger.warning(
                "TOOL_EXECUTION cheap stage skipped: "
                "could not import tool_execution_stage module. "
                "All tool calls will run on the expensive "
                "DIALOGUE model."
            )
            return None

        conversation_id = None
        wm = getattr(self, "_workflow_manager", None)
        if wm:
            conversation_id = getattr(wm, "_conversation_id", None)

        if not conversation_id or not self._tool_manager:
            self.logger.warning(
                "TOOL_EXECUTION cheap stage skipped: "
                "conversation_id=%s, tool_manager=%s. "
                "All tool calls will run on the expensive "
                "DIALOGUE model.",
                conversation_id,
                self._tool_manager,
            )
            return None

        chatbot_id = None
        chatbot = getattr(self, "chatbot", None)
        if chatbot:
            chatbot_id = getattr(chatbot, "id", None)

        from airunner_services.llm_workflow_events import (
            resolve_llm_workflow_event_sink,
        )

        event_sink = resolve_llm_workflow_event_sink(self)
        request_id = getattr(self, "_current_request_id", None)

        return run_tool_execution_stage(
            chat_model=cheap_model,
            tool_manager=self._tool_manager,
            prompt=prompt,
            conversation_id=conversation_id,
            selected_categories=selected_categories,
            chatbot_id=chatbot_id,
            event_sink=event_sink,
            request_id=request_id,
        )

    def _run_preflight(
        self, prompt: str
    ) -> Optional[Dict[str, Any]]:
        """Run safety pre-flight on the user message.

        Stores the result on self for the prompt builder to read.
        Returns a blocking response dict for HARD_BLOCK, else None.
        """
        from airunner_services.llm.safety.preflight import (
            PreflightOutcome,
            run_preflight,
        )

        self._preflight_result = run_preflight(prompt)
        if self._preflight_result.outcome == PreflightOutcome.HARD_BLOCK:
            self.logger.warning(
                "Pre-flight HARD_BLOCK — request rejected"
            )
            return {"messages": [], "blocked": True}
        return None

    def _set_cheap_stage_hint(self, stage_outcome: dict) -> None:
        """Store cheap-stage hints on self for per-turn injection.

        Called from the cheap-stage block in the request handling path.
        Hints (clarification notes and tool results) are stored on
        ``self._cheap_stage_hint`` so that
        :func:`_store_per_turn_context` can inject them into the
        human-turn block — NOT the system prompt, which would destroy
        the DIALOGUE model's persona and bust the prompt cache.
        """
        self._cheap_stage_hint = None
        hint_parts: list[str] = []
        clarification = stage_outcome.get("clarification_note")
        if clarification:
            hint_parts.append(
                f"[The tool system checked your last message and "
                f"determined: {clarification}. "
                f"Ask the user for the missing details "
                f"in your own voice — do NOT repeat this raw note.]"
            )
        tool_results = stage_outcome.get("tool_results", [])
        if tool_results:
            joined = "; ".join(tool_results)
            hint_parts.append(
                f"[The tool system already ran and got this "
                f"result: {joined}. "
                f"Relay this to the user in your own voice — "
                f"do NOT say you lack the ability to do this, "
                f"and do NOT repeat this raw note.]"
            )
        if hint_parts:
            self._cheap_stage_hint = "\n\n".join(hint_parts)
