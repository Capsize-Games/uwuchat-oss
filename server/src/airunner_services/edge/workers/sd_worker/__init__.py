"""Service-owned Stable Diffusion worker.

Decomposed into focused modules:

- ``_model_managers`` — model manager selection and properties
- ``_request_preparation`` — model signature tracking and request building
- ``_model_lifecycle`` — model load/unload lifecycle
- ``_signals`` — signal entry points and runtime control
- ``_llm_image`` — LLM-triggered image generation flow
- ``_message_handling`` — worker-thread message dispatch
- ``_daemon_generation`` — daemon-path art generation
- ``_finalize`` — generation finalization and error handling

``SDWorker`` is the composed public class; all existing importers keep
working unchanged.
"""

from __future__ import annotations

import threading
from typing import Optional

import torch

from airunner_services.contract_enums import (
    ArtVersion as StableDiffusionVersion,
)
from airunner_services.edge.model_management.sdxl_model_manager import (
    SDXLModelManager,
)
from airunner_services.edge.model_management.x4_upscale_manager import (
    X4UpscaleManager,
)
from airunner_services.edge.model_management.zimage_model_manager import (
    ZImageModelManager,
)
from airunner_services.edge.workers.sd_worker._daemon_generation import (
    SDWorkerDaemonGenerationMixin,
)
from airunner_services.edge.workers.sd_worker._finalize import (
    SDWorkerFinalizeMixin,
)
from airunner_services.edge.workers.sd_worker._llm_image import (
    SDWorkerLLMImageMixin,
)
from airunner_services.edge.workers.sd_worker._message_handling import (
    SDWorkerMessageHandlingMixin,
)
from airunner_services.edge.workers.sd_worker._model_lifecycle import (
    SDWorkerModelLifecycleMixin,
)
from airunner_services.edge.workers.sd_worker._model_managers import (
    SDWorkerModelManagersMixin,
)
from airunner_services.edge.workers.sd_worker._request_preparation import (
    SDWorkerRequestPreparationMixin,
)
from airunner_services.edge.workers.sd_worker._signals import (
    SDWorkerSignalsMixin,
)
from airunner_services.utils.application.enum_resolver import (
    model_action_type,
    signal_code_proxy,
)
from airunner_services.workers.worker import QueueType, Worker

ModelAction = model_action_type()
SignalCode = signal_code_proxy()

torch.backends.cuda.matmul.allow_tf32 = True


class SDWorker(
    SDWorkerModelManagersMixin,
    SDWorkerRequestPreparationMixin,
    SDWorkerModelLifecycleMixin,
    SDWorkerSignalsMixin,
    SDWorkerLLMImageMixin,
    SDWorkerMessageHandlingMixin,
    SDWorkerDaemonGenerationMixin,
    SDWorkerFinalizeMixin,
    Worker,
):
    queue_type = QueueType.GET_LAST_ITEM

    def __init__(self, image_export_worker):
        self.signal_handlers = {
            SignalCode.DO_GENERATE_SIGNAL: self.on_do_generate_signal,
            SignalCode.SD_LOAD_SIGNAL: self.on_load_art_signal,
            SignalCode.SD_UNLOAD_SIGNAL: self.on_unload_art_signal,
            SignalCode.INTERRUPT_IMAGE_GENERATION_SIGNAL: (
                self.on_interrupt_image_generation_signal
            ),
            SignalCode.CHANGE_SCHEDULER_SIGNAL: (
                self.on_change_scheduler_signal
            ),
            SignalCode.MODEL_STATUS_CHANGED_SIGNAL: (
                self.on_model_status_changed_signal
            ),
            SignalCode.SD_ART_MODEL_CHANGED: self.on_art_model_changed,
            SignalCode.LLM_IMAGE_PROMPT_GENERATED_SIGNAL: (
                self.on_llm_image_prompt_generated
            ),
        }
        self.image_export_worker = image_export_worker
        self._sdxl: Optional[SDXLModelManager] = None
        self._zimage: Optional[ZImageModelManager] = None
        self._sd: Optional[object] = None
        self._x4_upscaler: Optional[X4UpscaleManager] = None
        self._model_manager = None
        self._model_manager_lock = threading.Lock()
        self._version: StableDiffusionVersion = StableDiffusionVersion.NONE
        self._current_model = None
        self._current_version = None
        self._current_pipeline = None
        self._pending_scheduler: Optional[str] = None
        self._is_generating = False
        self._active_daemon_job_id: Optional[str] = None
        self._pending_daemon_unload_after_cancel = False
        self._llm_image_callback: Optional[object] = None
        self._cudnn_benchmark_applied = False
        super().__init__()
        # NOTE: cuDNN benchmark setup reads per-tenant ``memory_settings`` and
        # is deferred to the first handled message (which runs in tenant
        # context). Reading settings here, at eager startup construction, has
        # no tenant and would hit the tenant_anonymous schema.
        self._requested_action = ModelAction.NONE
        self._threads = []
        self._workers = []


__all__ = [
    "ModelAction",
    "QueueType",
    "SDWorker",
    "SignalCode",
    "Worker",
]
