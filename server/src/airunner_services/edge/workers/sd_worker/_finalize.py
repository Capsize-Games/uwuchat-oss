"""Generation finalization and error handling for SDWorker."""

from __future__ import annotations

from typing import Dict

import torch

from airunner_services.application_exceptions import PipeNotLoadedException
from airunner_services.settings import AIRUNNER_CUDA_OUT_OF_MEMORY_MESSAGE
from airunner_services.utils.application.enum_resolver import (
    signal_code_proxy,
)

SignalCode = signal_code_proxy()


class SDWorkerFinalizeMixin:
    """Finalize generation, report errors, and alert on missing models."""

    def _finalize_do_generate_signal(self, message: Dict):
        mm = self.model_manager
        self.logger.info(
            "[FINALIZE] _finalize_do_generate_signal called: "
            "mm=%s, mm._pipe=%s, model_is_loaded=%s",
            id(mm) if mm else None,
            getattr(mm, "_pipe", "N/A") if mm else "N/A",
            mm.model_is_loaded if mm else "N/A",
        )
        if mm:
            if not mm.model_is_loaded:
                if self._has_terminal_model_load_failure(mm):
                    self._notify_failed_model_load(
                        message.get("image_request", None)
                    )
                    return
                self.logger.info(
                    "Model not loaded yet, skipping generation "
                    "(download may be in progress)"
                )
                return

            try:
                self._is_generating = True
                mm.handle_generate_signal(message)
            except (PipeNotLoadedException, TypeError) as error:
                error_message = getattr(error, "message", str(error))
                self.handle_error(error_message)
                image_request = message.get("image_request", None)
                err = "Image model failed to load"
                if (
                    image_request is not None
                    and getattr(image_request, "model_path", None) == ""
                ):
                    err = "You must select a model before generating images."
                if image_request is not None and image_request.callback:
                    image_request.callback(err)
                self.send_missing_model_alert(err)
            except Exception as error:
                import traceback

                traceback_text = traceback.format_exc()
                error_message = str(error) or f"{type(error).__name__}"
                self.logger.exception(
                    "SDWorker: unhandled exception in handle_generate_signal"
                )
                self.handle_error(
                    f"Unexpected error: {error_message}\n{traceback_text}"
                )
                image_request = message.get("image_request", None)
                # Detect out-of-memory errors and provide a clear message
                oom_keywords = ("out of memory", "cuda out of memory")
                is_oom = isinstance(error, torch.cuda.OutOfMemoryError) or any(
                    kw in error_message.lower() for kw in oom_keywords
                )
                if is_oom:
                    failure_message = AIRUNNER_CUDA_OUT_OF_MEMORY_MESSAGE
                else:
                    failure_message = (
                        "An unexpected error occurred during image "
                        "generation. Please check logs."
                    )
                if image_request is not None and image_request.callback:
                    image_request.callback(failure_message)
                # Also emit the OOM as a missing-models alert so the
                # event system forwards it to subscribed WebSocket clients.
                self.send_missing_model_alert(failure_message)
            finally:
                self._is_generating = False
                if self._pending_scheduler is not None:
                    pending = self._pending_scheduler
                    self._pending_scheduler = None
                    self.logger.info(
                        "Applying deferred scheduler change to: %s",
                        pending,
                    )
                    self._apply_scheduler_change(pending)

    def handle_error(self, error_message):
        self.logger.error(f"SDWorker Error: {error_message}")

    def send_missing_model_alert(self, message):
        self.emit_signal(
            SignalCode.APPLICATION_STOP_SD_PROGRESS_BAR_SIGNAL,
            {"do_clear": True},
        )
        self.emit_signal(
            SignalCode.MISSING_REQUIRED_MODELS,
            {
                "title": "Model Not Found",
                "message": message,
            },
        )
