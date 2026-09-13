"""Model manager selection and properties for SDWorker."""

from __future__ import annotations

import os

from airunner_services.contract_enums import ArtVersion
from airunner_services.contract_enums import ArtVersion as StableDiffusionVersion
from airunner_services.contract_enums import normalize_art_version
from airunner_services.database.models import AIModels
from airunner_services.edge.model_management.sdxl_model_manager import (
    SDXLModelManager,
)
from airunner_services.edge.model_management.x4_upscale_manager import (
    X4UpscaleManager,
)
from airunner_services.edge.model_management.zimage_model_manager import (
    ZImageModelManager,
)
from airunner_services.utils.memory import apply_cudnn_benchmark


class SDWorkerModelManagersMixin:
    """Select and expose the active art model manager."""

    def _ensure_cudnn_benchmark(self) -> None:
        """Apply the cuDNN benchmark flag once, in tenant context."""
        if self._cudnn_benchmark_applied:
            return
        self._cudnn_benchmark_applied = True
        try:
            apply_cudnn_benchmark(self.memory_settings)
        except Exception:
            self.logger.exception("Failed to apply cuDNN benchmark setting")

    def _ensure_art_model_selected(self) -> None:
        """Auto-select a default art model when none is configured.

        The LLM ``generate_image`` tool doesn't pick a model the way the art
        panel does, so on a fresh install ``generator_settings.model`` is unset
        and the diffusers manager aborts with "No model selected". Select the
        first enabled txt2img model for the active version.
        """
        gs = self.generator_settings
        existing_id = getattr(gs, "model", None)
        if existing_id:
            existing = AIModels.objects.get(existing_id)
            if (
                existing is not None
                and existing.path
                and os.path.exists(existing.path)
            ):
                return

        version = (
            getattr(gs, "version", None) or ArtVersion.Z_IMAGE_TURBO.value
        )
        candidate = AIModels.objects.filter_by_first(
            model_type="art",
            version=version,
            pipeline_action="txt2img",
            enabled=True,
        )
        if candidate is None:
            # Fall back to any enabled txt2img art model.
            candidate = AIModels.objects.filter_by_first(
                model_type="art",
                pipeline_action="txt2img",
                enabled=True,
            )
        if candidate is None:
            self.logger.error(
                "LLM image: no art model available to auto-select "
                "(version=%s)",
                version,
            )
            return
        self.logger.info(
            "LLM image: auto-selected art model '%s' (id=%s, version=%s)",
            candidate.name,
            candidate.id,
            candidate.version,
        )
        self.update_generator_settings(
            model=candidate.id,
            version=candidate.version,
        )

    @property
    def version(self) -> StableDiffusionVersion:
        version = self._version
        if version is StableDiffusionVersion.NONE:
            version = StableDiffusionVersion(
                normalize_art_version(self.generator_settings.version)
            )
        if (
            self._version is StableDiffusionVersion.NONE
            and not self.application_settings.sd_enabled
        ):
            if version in (StableDiffusionVersion.Z_IMAGE_TURBO,):
                return version
            return StableDiffusionVersion.NONE
        return version

    @version.setter
    def version(self, value: StableDiffusionVersion):
        self._version = value

    @property
    def model_manager(self):
        with self._model_manager_lock:
            if self._model_manager is None:
                version = self.version

                if version in (ArtVersion.Z_IMAGE_TURBO,):
                    self._model_manager = self.zimage
                elif version in (
                    ArtVersion.SDXL1_0,
                    ArtVersion.SDXL_LIGHTNING,
                    ArtVersion.SDXL_HYPER,
                ):
                    self._model_manager = self.sdxl
                else:
                    raise ValueError(
                        f"Unsupported Stable Diffusion version: {version}"
                    )
            return self._model_manager

    @model_manager.setter
    def model_manager(self, value):
        with self._model_manager_lock:
            self._model_manager = value

    @property
    def zimage(self):
        if self._zimage is None:
            self._zimage = ZImageModelManager()
            self._zimage.image_export_worker = self.image_export_worker
        return self._zimage

    @property
    def sdxl(self):
        if self._sdxl is None:
            self._sdxl = SDXLModelManager()
            self._sdxl.image_export_worker = self.image_export_worker
        return self._sdxl

    @property
    def x4_upscaler(self):
        if self._x4_upscaler is None:
            self._x4_upscaler = X4UpscaleManager()
            self._x4_upscaler.image_export_worker = self.image_export_worker
        return self._x4_upscaler
