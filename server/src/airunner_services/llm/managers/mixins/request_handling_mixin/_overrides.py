"""Request-scoped model/service override mixin.

Extracted from ``RequestHandlingMixin``.  Applies request-scoped
dtype, provider, thinking, and reasoning-effort overrides and restores
the prior state after the request.
"""

from __future__ import annotations

from typing import Any, Optional

from airunner_services.contract_enums import ModelService
from airunner_services.llm.managers.request_preparation import (
    normalize_requested_dtype,
    normalize_requested_service,
)


class RequestOverrideMixin:
    """Apply and restore request-scoped model overrides."""

    def _requested_service(self, llm_request: Any) -> Optional[str]:
        """Return the requested service override, if any."""
        return normalize_requested_service(
            getattr(llm_request, "model_service", None)
        )

    def _apply_request_overrides(self, llm_request: Any) -> bool:
        """Apply request-scoped settings overrides and report changes."""
        settings_changed = False
        desired_dtype = normalize_requested_dtype(
            getattr(llm_request, "dtype", None)
        )
        if desired_dtype:
            settings_changed = self._apply_requested_dtype(desired_dtype)

        desired_service = self._requested_service(llm_request)
        if desired_service:
            settings_changed = (
                self._apply_requested_service(desired_service, llm_request)
                or settings_changed
            )

        return settings_changed

    def _apply_requested_dtype(self, desired_dtype: str) -> bool:
        """Apply one request-scoped dtype override when it changes."""
        current_dtype = normalize_requested_dtype(
            getattr(self.llm_generator_settings, "dtype", None)
        )
        if current_dtype == desired_dtype:
            return False

        self.logger.info(
            "[LLM] Switching dtype %s -> %s for request",
            current_dtype,
            desired_dtype,
        )
        self.llm_generator_settings.dtype = desired_dtype
        return True

    def _current_service(self) -> str:
        """Return the currently active LLM provider kind."""
        if getattr(self.llm_settings, "use_openrouter", False):
            return ModelService.OPENROUTER.value
        if getattr(self.llm_settings, "use_ollama", False):
            return ModelService.OLLAMA.value
        return ModelService.LOCAL.value

    def _apply_requested_service(
        self,
        desired_service: str,
        llm_request: Any,
    ) -> bool:
        """Apply provider flags and request-level model overrides."""
        current_service = self._current_service()
        settings_changed = current_service != desired_service
        if current_service != desired_service:
            self.logger.info(
                "[LLM] Switching model_service %s -> %s for request",
                current_service,
                desired_service,
            )

        self.llm_settings.use_openrouter = (
            desired_service == ModelService.OPENROUTER.value
        )
        self.llm_settings.use_ollama = (
            desired_service == ModelService.OLLAMA.value
        )
        self.llm_settings.use_local_llm = (
            desired_service == ModelService.LOCAL.value
        )

        api_model = getattr(llm_request, "api_model", None)
        if isinstance(api_model, str) and api_model.strip():
            api_model = api_model.strip()
            if desired_service == ModelService.OPENROUTER.value:
                if getattr(self.llm_settings, "model", None) != api_model:
                    self.llm_settings.model = api_model
                    settings_changed = True
            elif desired_service == ModelService.OLLAMA.value:
                if (
                    getattr(self.llm_settings, "ollama_model", None)
                    != api_model
                ):
                    self.llm_settings.ollama_model = api_model
                    settings_changed = True

        return settings_changed

    def _apply_request_thinking_override(
        self,
        llm_request: Any,
    ) -> list[tuple[Any, Any]]:
        """Patch thinking flags on active chat models for one request."""
        thinking_override = getattr(llm_request, "enable_thinking", None)
        thinking_patches: list[tuple[Any, Any]] = []
        if thinking_override is None:
            return thinking_patches

        targets = [self._chat_model]
        if self._workflow_manager:
            targets.append(
                getattr(self._workflow_manager, "_chat_model", None)
            )
            targets.append(
                getattr(self._workflow_manager, "_original_chat_model", None)
            )

        for target in targets:
            if target is None or not hasattr(target, "enable_thinking"):
                continue
            try:
                thinking_patches.append(
                    (target, getattr(target, "enable_thinking"))
                )
                setattr(target, "enable_thinking", bool(thinking_override))
            except Exception:
                continue
        return thinking_patches

    def _restore_thinking_patches(
        self,
        thinking_patches: list[tuple[Any, Any]],
    ) -> None:
        """Restore chat-model thinking flags after request completion."""
        for target, original in thinking_patches:
            try:
                setattr(target, "enable_thinking", original)
            except Exception:
                continue

    def _apply_request_reasoning_effort_override(
        self,
        llm_request: Any,
    ) -> list[tuple[Any, Any]]:
        """Patch GPT-OSS reasoning effort on active chat models for one request."""
        reasoning_effort = getattr(llm_request, "reasoning_effort", None)
        if isinstance(reasoning_effort, str):
            reasoning_effort = reasoning_effort.strip().lower() or None
        if reasoning_effort not in {"low", "medium", "high"}:
            return []

        reasoning_patches: list[tuple[Any, Any]] = []
        targets = [self._chat_model]
        if self._workflow_manager:
            targets.append(
                getattr(self._workflow_manager, "_chat_model", None)
            )
            targets.append(
                getattr(self._workflow_manager, "_original_chat_model", None)
            )

        for target in targets:
            if target is None or not hasattr(target, "reasoning_effort"):
                continue
            try:
                reasoning_patches.append(
                    (target, getattr(target, "reasoning_effort"))
                )
                setattr(target, "reasoning_effort", reasoning_effort)
            except Exception:
                continue

        return reasoning_patches

    def _restore_reasoning_effort_patches(
        self,
        reasoning_patches: list[tuple[Any, Any]],
    ) -> None:
        """Restore chat-model GPT-OSS reasoning effort after request completion."""
        for target, original in reasoning_patches:
            try:
                setattr(target, "reasoning_effort", original)
            except Exception:
                continue
