"""Model signature tracking and image request preparation."""

from __future__ import annotations

import os
from typing import Dict, Optional

from airunner_services.contract_enums import (
    ArtVersion as StableDiffusionVersion,
)
from airunner_services.contract_enums import normalize_art_version
from airunner_services.database.models import AIModels
from airunner_services.edge.art.stablediffusion.image_request import (
    ImageRequest,
)


class SDWorkerRequestPreparationMixin:
    """Resolve model paths and build ImageRequest payloads."""

    def _requested_model_signature(
        self,
        image_request: Optional[ImageRequest],
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Return the requested model signature for one generation."""
        model_path = self._get_model_path_from_image_request(image_request)
        if image_request is not None:
            version = getattr(image_request, "version", None)
            pipeline_action = getattr(image_request, "pipeline_action", None)
        else:
            version = getattr(self.generator_settings, "version", None)
            pipeline_action = getattr(
                self.generator_settings,
                "pipeline_action",
                None,
            )
        return model_path, version, pipeline_action

    def _record_loaded_model_signature(
        self,
        image_request: Optional[ImageRequest],
    ) -> None:
        """Record the active model signature after a successful load."""
        (
            self._current_model,
            self._current_version,
            self._current_pipeline,
        ) = self._requested_model_signature(image_request)

    def _clear_loaded_model_signature(self) -> None:
        """Forget the active model signature after unload."""
        self._current_model = None
        self._current_version = None
        self._current_pipeline = None

    def _get_model_path_from_image_request(
        self,
        image_request: Optional[ImageRequest],
    ) -> Optional[str]:
        model_path = None

        if image_request is not None:
            model_path = image_request.model_path

        if model_path is None:
            custom_path = getattr(self.generator_settings, "custom_path", None)
            if custom_path is not None and custom_path != "":
                if os.path.exists(custom_path):
                    model_path = custom_path

        generator_model = getattr(self.generator_settings, "model", None)
        if (
            model_path is None or model_path == ""
        ) and generator_model is not None:
            aimodel = AIModels.objects.get(generator_model)
            if aimodel is not None:
                model_path = aimodel.path

        return model_path

    def _debug_log_model_path_resolution(
        self,
        image_request: Optional[ImageRequest],
        model_path: Optional[str],
    ):
        try:
            self.logger.debug(
                "Model path resolution: image_request.model_path=%s "
                "generator_settings.model=%s "
                "generator_settings.custom_path=%s resolved=%s",
                getattr(image_request, "model_path", None),
                getattr(self.generator_settings, "model", None),
                getattr(self.generator_settings, "custom_path", None),
                model_path,
            )
        except Exception:
            pass

    def _process_image_request(self, data: Dict) -> Dict:
        settings = self.generator_settings
        image_request = data.get("image_request", None)
        model_path = self._get_model_path_from_image_request(image_request)
        try:
            self._debug_log_model_path_resolution(image_request, model_path)
        except Exception:
            pass

        if image_request is not None:
            version = normalize_art_version(image_request.version)
            image_request.version = version
        else:
            version = normalize_art_version(settings.version)
            data["image_request"] = ImageRequest(
                pipeline_action=settings.pipeline_action,
                generator_name=settings.generator_name,
                prompt=settings.prompt,
                negative_prompt=settings.negative_prompt,
                second_prompt=settings.second_prompt,
                second_negative_prompt=settings.second_negative_prompt,
                random_seed=settings.random_seed,
                model_path=model_path,
                scheduler=settings.scheduler,
                version=version,
                use_compel=settings.use_compel,
                steps=settings.steps,
                ddim_eta=settings.ddim_eta,
                scale=settings.scale / 100,
                seed=settings.seed,
                strength=settings.strength / 100,
                n_samples=settings.n_samples,
                images_per_batch=settings.images_per_batch,
                clip_skip=settings.clip_skip,
                crops_coords_top_left=settings.crops_coords_top_left,
                negative_crops_coords_top_left=(
                    settings.negative_crops_coords_top_left
                ),
                original_size=settings.original_size,
                target_size=settings.target_size,
                negative_original_size=settings.negative_original_size,
                negative_target_size=settings.negative_target_size,
                width=self.application_settings.working_width,
                height=self.application_settings.working_height,
            )
            # Apply LLM-triggered post-generation callback if set
            if self._llm_image_callback is not None:
                data["image_request"].callback = self._llm_image_callback
        new_version = StableDiffusionVersion(version)
        if new_version is not self.version:
            # Switching versions uses a *different* manager instance (e.g.
            # Z-Image → SDXL). Fully unload the current version's pipeline
            # first, otherwise its weights stay resident in VRAM and loading
            # the new version OOMs. (Within-version model changes reuse the
            # same manager and unload via reload(), so they're unaffected.)
            self.unload_model_manager()
            self.version = new_version
        return data
