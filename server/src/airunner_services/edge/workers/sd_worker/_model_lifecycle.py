"""Model load/unload lifecycle for SDWorker."""

from __future__ import annotations

from typing import Dict, Optional

from airunner_services.contract_enums import ModelStatus
from airunner_services.contract_enums import ModelType
from airunner_services.edge.art.runtime_memory import clear_memory
from airunner_services.edge.art.stablediffusion.image_request import (
    ImageRequest,
)
from airunner_services.utils.application.enum_resolver import (
    model_action_type,
)

ModelAction = model_action_type()


class SDWorkerModelLifecycleMixin:
    """Load, unload, and reload art model managers."""

    def load_model_manager(self, data: Dict = None):
        data = data or {}
        data["settings"] = self.generator_settings
        data = self._process_image_request(data)
        do_reload = data.get("do_reload", False)
        mm = self.model_manager
        self.logger.info(
            "[LOAD] load_model_manager: mm=%s, mm._pipe=%s, "
            "model_is_loaded=%s",
            id(mm),
            getattr(mm, "_pipe", "N/A"),
            mm.model_is_loaded if mm else "N/A",
        )
        image_request = data.get("image_request")
        requested_signature = self._requested_model_signature(image_request)
        if (
            mm
            and mm.model_is_loaded
            and requested_signature
            != (
                self._current_model,
                self._current_version,
                self._current_pipeline,
            )
        ):
            do_reload = True
        if mm and image_request is not None:
            try:
                mm.image_request = image_request
            except Exception:
                pass
        if mm:
            if do_reload:
                self.logger.info("[LOAD] Reloading model")
                mm.reload()
            elif not mm.model_is_loaded:
                self.logger.info(
                    "[LOAD] Loading model: path=%s version=%s",
                    getattr(image_request, "model_path", None),
                    getattr(image_request, "version", None),
                )
                mm.load()
                self.logger.info(
                    "[LOAD] load() returned: model_is_loaded=%s " "pipe=%s",
                    mm.model_is_loaded,
                    getattr(mm, "_pipe", "N/A") is not None,
                )
            try:
                self.logger.debug(
                    "[LOAD DEBUG] After load: mm._pipe=%s, mm=%s",
                    getattr(mm, "_pipe", "N/A"),
                    id(mm),
                )
            except Exception:
                pass
            if mm.model_is_loaded:
                self._record_loaded_model_signature(image_request)
        if data and mm and mm.model_is_loaded:
            callback = data.get("callback", None)
            if callback is not None:
                self.logger.info(
                    "[LOAD] Model loaded, calling generation " "callback"
                )
                callback(data)
        elif data and mm and self._has_terminal_model_load_failure(mm):
            self.logger.error("[LOAD] Model load FAILED")
            callback = data.get("callback", None)
            if callback is not None:
                callback(data)
        elif data and mm:
            self.logger.info(
                "[LOAD] Model not loaded and not failed — "
                "download may be in progress or loading "
                "still running"
            )

    @staticmethod
    def _has_terminal_model_load_failure(model_manager) -> bool:
        try:
            return (
                model_manager.model_status.get(model_manager.model_type)
                is ModelStatus.FAILED
            )
        except Exception:
            return False

    def _notify_failed_model_load(
        self,
        image_request: Optional[ImageRequest],
    ) -> None:
        err = "Image model failed to load"
        if image_request is not None:
            if getattr(image_request, "model_path", None) == "":
                err = "You must select a model before generating images."
            if image_request.callback:
                image_request.callback(err)
        self.send_missing_model_alert(err)

    def unload(self, data: Dict):
        self.add_to_queue(
            {
                "action": ModelAction.UNLOAD,
                "type": ModelType.SD,
                "data": data,
            }
        )

    def unload_model_manager(self, data: Dict = None):
        if self._model_manager is not None:
            manager_ref = self._model_manager
            self._model_manager.unload()
            self.model_manager = None

            if manager_ref is self._sd:
                self.logger.info(">>> Unloading SD model manager")
                self._sd.image_export_worker.stop()
                del self._sd.image_export_worker
                self._sd.image_export_worker = None
                del self._sd
                self._sd = None
            elif manager_ref is self._sdxl:
                self.logger.info(">>> Unloading SDXL model manager")
                self._sdxl.image_export_worker.stop()
                del self._sdxl.image_export_worker
                self._sdxl.image_export_worker = None
                del self._sdxl
                self._sdxl = None
            elif manager_ref is self._zimage:
                self.logger.info(">>> Unloading Z-Image model manager")
                self._zimage.image_export_worker.stop()
                del self._zimage.image_export_worker
                self._zimage.image_export_worker = None
                del self._zimage
                self._zimage = None
            elif manager_ref is self._x4_upscaler:
                self.logger.info(">>> Unloading X4 Upscaler model manager")
                self._x4_upscaler.image_export_worker.stop()
                del self._x4_upscaler.image_export_worker
                self._x4_upscaler.image_export_worker = None
                del self._x4_upscaler
                self._x4_upscaler = None

            self._clear_loaded_model_signature()

            # Drop the last strong reference to the unloaded manager and
            # return the freed device memory to the driver. unload() empties
            # the cache while the manager (compel, generator, etc.) is still
            # alive, so without this final clear the GPU memory those held is
            # not released back to the OS/NVML until the next allocation.
            del manager_ref
            clear_memory()

        if data:
            callback = data.get("callback", None)
            if callback is not None:
                callback(data)

    def _load_controlnet(self):
        if self.model_manager:
            self.model_manager.load_controlnet()

    def _unload_controlnet(self):
        if self.model_manager:
            self.model_manager.unload_controlnet()
