"""Request orchestration entry-point mixin.

Extracted from ``RequestHandlingMixin``.  ``handle_request`` is the
top-level orchestrator: it applies overrides, prepares conversation,
tooling, RAG, and document context, runs the cheap tool-execution
stage, then delegates to ``do_generate``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from airunner_services.database.models.llm_generator_settings import (
    LLMGeneratorSettings,
)
from airunner_services.llm.managers.mixins.request_handling_mixin._rewrite import (
    _maybe_rewrite_data_prompt,
)
from airunner_services.llm.managers.request_preparation import (
    capture_request_settings_snapshot,
    restore_request_settings_snapshot,
)


class RequestHandlingCoreMixin:
    """Top-level request orchestration for LLM generation."""

    _pii_vault: Any = None

    def _ensure_pii_vault(self) -> None:
        """Create and thread a per-request PII vault when masking is enabled.

        Called early in every ``handle_request`` call, for both cloud and
        edge model managers. Disposes of any prior vault first (safety
        net).
        """
        self._clear_pii_vault()
        try:
            from airunner_services.llm.pii.settings import (
                PII_MASKING_ENABLED,
            )
        except ImportError:
            return
        if not PII_MASKING_ENABLED:
            return
        try:
            from airunner_services.llm.pii.vault import PIIVault

            self._pii_vault = PIIVault()
            if self._tool_manager is not None:
                self._tool_manager.set_active_vault(self._pii_vault)
            if self._workflow_manager is not None:
                self._workflow_manager._pii_vault = self._pii_vault
            self.logger.info("PII vault created for request")
        except Exception:
            self.logger.exception("Failed to create PII vault")

    def _clear_pii_vault(self) -> None:
        """Dispose of the current request's PII vault."""
        if self._pii_vault is not None:
            self._pii_vault = None
        if self._tool_manager is not None:
            self._tool_manager.clear_active_vault()
        if self._workflow_manager is not None:
            self._workflow_manager._pii_vault = None
        if self._workflow_manager and hasattr(
            self._workflow_manager, "set_interrupted"
        ):
            self._workflow_manager.set_interrupted(True)

    async def handle_request(
        self,
        data: Dict,
        extra_context: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Handle an incoming request for LLM generation."""
        prompt_text = str(
            data.get("request_data", {}).get("prompt", "")
        )
        self.logger.info(
            "HANDLE_REQ prompt_chars=%d action=%s conv_id=%s stateless=%s",
            len(prompt_text),
            data.get("request_data", {}).get("action"),
            data.get("conversation_id"),
            getattr(
                (data.get("request_data", {}) or {}).get(
                    "llm_request", None
                ),
                "stateless",
                False,
            ) if data.get("request_data", {}).get("llm_request") else False,
        )
        self.logger.info("handle_request called on instance %s", id(self))
        self._invalidate_setting_cache(LLMGeneratorSettings)

        self._current_request_id = data.get("request_id")
        if not self._current_request_id:
            self.logger.warning(
                "[REQUEST] Missing request_id on incoming request; "
                "streaming responses will not be routed"
            )
        else:
            self.logger.debug(
                "[REQUEST] Set _current_request_id=%s",
                self._current_request_id,
            )

        self._interrupted = False
        if self._chat_model and hasattr(self._chat_model, "set_interrupted"):
            self._chat_model.set_interrupted(False)
        if self._workflow_manager and hasattr(
            self._workflow_manager,
            "set_interrupted",
        ):
            self._workflow_manager.set_interrupted(False)

        llm_request = data["request_data"].get("llm_request")
        self.llm_request = llm_request
        if llm_request is not None:
            try:
                setattr(
                    llm_request,
                    "prompt",
                    data["request_data"].get("prompt", ""),
                )
            except Exception:
                pass

        settings_snapshot = capture_request_settings_snapshot(self)
        request_settings_changed = self._apply_request_overrides(llm_request)
        if request_settings_changed:
            self.unload()

        # Per-conversation DIALOGUE routing (Decision B): ask the active
        # project's optional dialogue_routing module whether this
        # conversation should use the local chat daemon instead of the
        # static cloud default (code mode OFF). Rebuild the chat model
        # via the existing unload/load machinery when the routing
        # changed so model, workflow, and tool bindings are all built
        # from the routed settings. The mutation is folded into the
        # request-scoped snapshot/restore: when it changes the settings,
        # `request_settings_changed` becomes True so the snapshot taken
        # above is restored after this request (the static cloud default
        # is the true baseline, never a previous request's local state).
        # No-op for projects without the module. The request's own
        # conversation id is used (the workflow manager's is only set
        # later in conversation preparation).
        raw_conv_id = data.get("conversation_id")
        request_conv_id = (
            int(raw_conv_id) if str(raw_conv_id or "").isdigit() else None
        )
        routing_changed = self._apply_dialogue_conversation_routing(
            request_conv_id, llm_request=llm_request
        )
        if routing_changed:
            request_settings_changed = True
            self.unload()

        self.load()

        # ---- PII masking: create per-request vault BEFORE any LLM call ----
        # Must run before both the stateless branch and the streaming branch
        # so _pii_vault is available for masking regardless of which path
        # the request takes.  Also clears any stale vault from a prior
        # request on this per-worker singleton.
        self._ensure_pii_vault()
        # ---- end PII ----

        # Stateless one-shot completion (e.g. character generation): bypass the
        # chat agent entirely. No conversation/chatbot is created and nothing is
        # persisted. Must run after load() so the chat model is ready.
        if getattr(llm_request, "stateless", False):
            try:
                return self._do_stateless_generate(
                    data["request_data"].get("prompt", ""),
                    getattr(llm_request, "system_prompt", None),
                    llm_request,
                )
            finally:
                self._clear_pii_vault()

        request_tool_defaults = self._request_tool_defaults(data)

        self._prepare_request_memory(llm_request)
        self._prepare_request_conversation(data, llm_request)

        # Thread the resolved agent (chatbot + user) into ToolManager
        # so requires_agent tools receive real context instead of None.
        self._thread_agent_to_tool_manager()

        # ── Prompt-rewrite stage ──────────────────────────────────
        # Runs BEFORE _prepare_request_tooling so a rewritten prompt
        # reaches TOOL_CLASSIFICATION and can change which categories
        # apply.  Returns separate rewritten text; the original
        # data["request_data"]["prompt"] is NEVER mutated — it stays
        # the user's literal message for persistence and display.
        rewritten_prompt = _maybe_rewrite_data_prompt(self, data)

        tools_filtered, selected_categories, system_prompt = (
            self._prepare_request_tooling(
                data, llm_request,
                prompt_override=rewritten_prompt,
            )
        )
        self._prepare_request_rag(data, llm_request, selected_categories)
        self._prepare_request_document_context(data, llm_request)
        thinking_patches = self._apply_request_thinking_override(llm_request)
        reasoning_patches = self._apply_request_reasoning_effort_override(
            llm_request
        )

        if request_tool_defaults and self._tool_manager:
            self._tool_manager.set_request_tool_defaults(request_tool_defaults)

        prompt = data["request_data"]["prompt"]

        # Mint the call_chain_id here, before any stage that needs it,
        # so tool_execution_stage (line 128) and every subsequent stage
        # share one stable ID per turn.
        import uuid
        self._call_chain_id = str(uuid.uuid4())
        from airunner_services.llm.active_call_chain import (
            set_active_call_chain,
        )
        set_active_call_chain(self._call_chain_id)

        preflight = self._run_preflight(prompt)
        if preflight is not None:
            return preflight

        # ── Cheap-model tool-execution stage ──────────────────────
        # Runs selected tool categories on a cheap model before the
        # DIALOGUE model, persisting tool results to conversation
        # history so Haiku sees them as context for its reply.
        # _maybe_run_tool_execution_stage receives the rewritten
        # prompt so it searches for the scoped-down framing.  The
        # original prompt stays for DIALOGUE's _do_generate.
        exec_prompt = rewritten_prompt or prompt
        stage_outcome = self._maybe_run_tool_execution_stage(
            prompt=exec_prompt,
            selected_categories=selected_categories,
            llm_request=llm_request,
        )
        if stage_outcome:
            # Strip every category the cheap stage was asked to
            # handle — whether it successfully executed tools,
            # hit a ceiling, or only produced a clarification
            # note — so DIALOGUE never independently continues a
            # tool category that was already delegated.
            attempted = set(
                stage_outcome.get("attempted_categories", [])
            ) or set(stage_outcome.get("executed_categories", []))
            if attempted:
                remaining = [
                    c for c in selected_categories
                    if c not in attempted
                ]
                action = data["request_data"].get("action")
                self._apply_tool_filter(
                    tool_categories=remaining,
                    action=action,
                    force_tool=getattr(
                        llm_request, "force_tool", None
                    ),
                )
                if llm_request:
                    llm_request.tool_categories = remaining
                tools_filtered = True
            self._set_cheap_stage_hint(stage_outcome)

        try:
            return await self._do_generate(
                prompt=prompt,
                action=data["request_data"]["action"],
                system_prompt=system_prompt,
                llm_request=data["request_data"]["llm_request"],
                extra_context=extra_context,
                skip_tool_setup=tools_filtered,
            )
        finally:
            self._restore_thinking_patches(thinking_patches)
            self._restore_reasoning_effort_patches(reasoning_patches)
            if request_tool_defaults and self._tool_manager:
                self._tool_manager.clear_request_tool_defaults()
            if request_settings_changed:
                restore_request_settings_snapshot(
                    self,
                    settings_snapshot,
                )
                self.unload()
