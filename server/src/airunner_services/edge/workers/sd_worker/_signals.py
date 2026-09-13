"""Signal entry points and runtime control for SDWorker."""

from __future__ import annotations

from typing import Dict

from airunner_services.contract_enums import ModelType
from airunner_services.database.models import GeneratorSettings
from airunner_services.utils.application.enum_resolver import (
    model_action_type,
    signal_code_proxy,
)

ModelAction = model_action_type()
SignalCode = signal_code_proxy()


class SDWorkerSignalsMixin:
    """Handle signal entry points and scheduler/interrupt control."""

    def on_load_controlnet_signal(self, data=None):
        self.add_to_queue(
            {
                "action": ModelAction.LOAD,
                "type": ModelType.CONTROLNET,
                "data": data,
            }
        )

    def on_input_image_settings_changed_signal(self, data: Dict):
        if self.model_manager:
            self.model_manager.settings_changed(data)

    def on_unload_controlnet_signal(self, _data=None):
        if self.model_manager:
            self._unload_controlnet()

    def on_load_art_signal(self, data: Dict = None):
        self.add_to_queue(
            {
                "action": ModelAction.LOAD,
                "type": ModelType.SD,
                "data": data,
            }
        )

    def on_unload_art_signal(self, data: Dict = None):
        self.add_to_queue(
            {
                "action": ModelAction.UNLOAD,
                "type": ModelType.SD,
                "data": data,
            }
        )

    def on_art_model_changed(self, data: Dict = None):
        self._invalidate_setting_cache(GeneratorSettings)
        self.unload_model_manager()

    def on_tokenizer_load_signal(self, data: Dict = None):
        if self.model_manager:
            self.model_manager.sd_load_tokenizer(data)

    @staticmethod
    def on_sd_cancel_signal(_data=None):
        print("on_sd_cancel_signal")

    def on_start_auto_image_generation_signal(self, _data=None):
        pass

    def on_stop_auto_image_generation_signal(self, _data=None):
        pass

    def on_do_generate_signal(self, message: Dict):
        print(
            "[SDWorker] on_do_generate_signal received, "
            "queuing generate action"
        )
        self.add_to_queue(
            {
                "action": ModelAction.GENERATE,
                "type": ModelType.SD,
                "message": message,
            }
        )

    def request_daemon_unload_after_cancel(self) -> bool:
        """Unload the daemon art runtime after the active job finishes."""
        if self._active_daemon_job_id is None:
            return False
        self._pending_daemon_unload_after_cancel = True
        return True

    def _emit_pending_daemon_unload_if_requested(self) -> None:
        """Emit one deferred unload after a daemon art job exits."""
        if not self._pending_daemon_unload_after_cancel:
            return
        self._pending_daemon_unload_after_cancel = False
        self.emit_signal(SignalCode.SD_UNLOAD_SIGNAL, {})

    def on_interrupt_image_generation_signal(self, _data=None):
        client = self._daemon_client()
        if client is not None and self._active_daemon_job_id is not None:
            try:
                client.cancel_art_job(
                    self._active_daemon_job_id,
                    auto_start=False,
                )
            except RuntimeError:
                pass
            return
        if self.model_manager:
            self.model_manager.interrupt_image_generation()

    def on_change_scheduler_signal(self, data: Dict):
        scheduler_name = data["scheduler"]
        self.update_generator_settings(scheduler=scheduler_name)

        if self._is_generating:
            self.logger.debug(
                "[SCHEDULER] Deferring scheduler change to '%s' until "
                "generation completes",
                scheduler_name,
            )
            self._pending_scheduler = scheduler_name
        elif self.model_manager:
            self.model_manager._load_scheduler(scheduler_name)

    def _apply_scheduler_change(self, scheduler_name: str):
        """Apply a scheduler change after a deferred generation ends."""
        if self.model_manager:
            self.model_manager._load_scheduler(scheduler_name)

    def on_model_status_changed_signal(self, message: Dict):
        if message.get("model") != ModelType.SD:
            return
        if self._model_manager is None:
            return
        if self._requested_action is ModelAction.CLEAR:
            self.on_unload_art_signal()
        self._requested_action = ModelAction.NONE
