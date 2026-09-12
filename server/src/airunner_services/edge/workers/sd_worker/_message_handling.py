"""Worker-thread message dispatch for SDWorker."""

from __future__ import annotations

from typing import Dict, Optional

from airunner_services.contract_enums import ModelType
from airunner_services.utils.application.enum_resolver import (
    model_action_type,
)

ModelAction = model_action_type()


class SDWorkerMessageHandlingMixin:
    """Run the worker loop and dispatch queued messages."""

    def start_worker_thread(self):
        if not self.application_settings.sd_enabled:
            return
        model_manager = self.model_manager
        if model_manager is not None:
            model_manager.load()

    def handle_message(self, message: Optional[Dict] = None):
        if message is None:
            return

        self._ensure_cudnn_benchmark()
        action = message.get("action", None)
        model_type = message.get("type", None)
        data = (
            message.get("message")
            if "message" in message
            else message.get("data", {})
        )

        self.logger.debug(
            "[HANDLE_MESSAGE] action=%s, model_type=%s",
            action,
            model_type,
        )

        if action is None or model_type is None:
            return

        if action is ModelAction.LOAD:
            if model_type is ModelType.SD:
                self.load_model_manager(data)
            elif model_type is ModelType.CONTROLNET:
                self._load_controlnet()
        elif action == ModelAction.UNLOAD:
            if model_type is ModelType.SD:
                self.unload_model_manager(data)
            elif model_type is ModelType.CONTROLNET:
                self._unload_controlnet()
        elif action is ModelAction.GENERATE:
            if model_type is ModelType.SD:
                self._generate_image(data)
