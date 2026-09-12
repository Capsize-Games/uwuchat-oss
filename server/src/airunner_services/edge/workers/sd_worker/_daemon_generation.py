"""Daemon-path art generation for SDWorker."""

from __future__ import annotations

import base64
import io
from functools import partial
from typing import Dict, Optional

from PIL import Image

from airunner_services.contract_enums import GeneratorSection
from airunner_services.contract_enums import ModelService
from airunner_services.edge.art.stablediffusion.image_request import (
    ImageRequest,
)
from airunner_services.edge.art.stablediffusion.image_response import (
    ImageResponse,
)
from airunner_services.utils.application.api_reference import (
    peek_registered_api,
)
from airunner_services.utils.image import convert_image_to_binary


class SDWorkerDaemonGenerationMixin:
    """Generate images through the daemon art runtime."""

    def _generate_image(self, message: Dict):
        image_request = message.get("image_request")
        client = self._daemon_client()
        path_label = "daemon" if client is not None else ModelService.LOCAL.value
        print(
            f"[SDWorker._generate_image] path={path_label} "
            f"version={getattr(image_request, 'version', None)} "
            f"model={getattr(image_request, 'model_path', None)}"
        )
        self.logger.info(
            "SDWorker::_generate_image using %s path for version=%s "
            "model=%s",
            "daemon" if client is not None else ModelService.LOCAL.value,
            getattr(image_request, "version", None),
            getattr(image_request, "model_path", None),
        )
        if client is not None:
            self._generate_image_via_daemon(message)
            return
        print("[SDWorker._generate_image] Loading model manager locally")
        message["callback"] = self._finalize_do_generate_signal
        self.load_model_manager(message)

    def _daemon_client(self):
        api = peek_registered_api()
        return getattr(api, "daemon_client", None) if api else None

    @staticmethod
    def _encode_daemon_image(image: Optional[Image.Image]) -> Optional[str]:
        """Return one PNG base64 payload for daemon art requests."""
        if image is None:
            return None
        binary = convert_image_to_binary(image.convert("RGB"))
        if not binary:
            return None
        return base64.b64encode(binary).decode("ascii")

    def _generate_image_via_daemon(self, message: Dict) -> None:
        client = self._daemon_client()
        image_request = message.get("image_request")
        if client is None or not isinstance(image_request, ImageRequest):
            self.handle_error(
                "No image request available for daemon art generation"
            )
            return

        total_steps = max(int(image_request.steps or 1), 1)
        pipeline = getattr(
            image_request.generator_section,
            "value",
            GeneratorSection.TXT2IMG.value,
        )
        image_b64 = self._encode_daemon_image(image_request.image)
        error_message: Optional[str] = None
        image_bytes: Optional[bytes] = None

        def on_progress(status: Dict) -> None:
            try:
                progress = float(status.get("progress") or 0.0)
            except (TypeError, ValueError):
                return
            self.logger.debug(
                "SDWorker daemon art progress: status=%s progress=%.1f",
                status.get("status"),
                progress,
            )
            step = int(round((progress / 100.0) * total_steps))
            step = max(0, min(total_steps, step))

        try:
            self.logger.info(
                "Submitting daemon art job for version=%s scheduler=%s "
                "model=%s",
                image_request.version,
                image_request.scheduler,
                image_request.model_path,
            )
            job = client.start_art_generation(
                prompt=image_request.prompt,
                negative_prompt=image_request.negative_prompt or "",
                width=image_request.width,
                height=image_request.height,
                steps=image_request.steps,
                cfg_scale=image_request.scale,
                seed=(
                    None if image_request.random_seed else image_request.seed
                ),
                num_images=image_request.n_samples,
                model=image_request.model_path or None,
                version=image_request.version or None,
                scheduler=image_request.scheduler or None,
                pipeline=pipeline,
                strength=image_request.strength,
                image_b64=image_b64,
                skip_auto_export=True,
            )
            job_id = str(job.get("job_id", "") or "")
            if not job_id:
                raise RuntimeError("Art generation did not return a job id")
            self._active_daemon_job_id = job_id
            self.logger.info("Daemon art job accepted: job_id=%s", job_id)
            image_bytes = client.wait_art_job(
                job_id,
                auto_start=False,
                progress_callback=on_progress,
            )
            self.logger.info(
                "Daemon art job completed: job_id=%s bytes=%s",
                job_id,
                len(image_bytes),
            )
        except RuntimeError as exc:
            error_message = str(exc)
        finally:
            self._active_daemon_job_id = None

        if error_message is not None:
            self._handle_daemon_art_error(error_message)
            self._emit_pending_daemon_unload_if_requested()
            return

        if image_bytes is None:
            return

        try:
            self._publish_daemon_art_result(
                message,
                image_request,
                image_bytes,
            )
        finally:
            self._emit_pending_daemon_unload_if_requested()

    def _handle_daemon_art_error(self, message: str) -> None:
        self.handle_error(message)

    def _publish_daemon_art_result(
        self,
        message: Dict,
        image_request: ImageRequest,
        image_bytes: bytes,
    ) -> None:
        image = Image.open(io.BytesIO(image_bytes)).copy()
        data = self._daemon_result_data(image_request)
        export_callback = partial(
            self._queue_post_display_export,
            image,
            data,
        )
        response = ImageResponse(
            images=[image],
            data=data,
            active_rect=message.get("active_rect"),
            is_outpaint=(
                image_request.generator_section is GeneratorSection.OUTPAINT
            ),
            node_id=image_request.node_id,
            post_display_callback=export_callback,
        )
        sent_to_canvas = False
        if not sent_to_canvas:
            export_callback()
        if image_request.callback:
            image_request.callback(response)

    def _queue_post_display_export(
        self,
        image: Image.Image,
        data: Dict,
    ) -> None:
        """Queue auto export after the canvas handoff has been posted."""
        self.image_export_worker.add_to_queue(
            {"images": [image.copy()], "data": data}
        )

    def _daemon_result_data(self, image_request: ImageRequest) -> Dict:
        generator_section = image_request.generator_section
        return {
            "current_prompt": image_request.prompt,
            "current_negative_prompt": image_request.negative_prompt,
            "image_request": image_request,
            "guidance_scale": image_request.scale,
            "num_inference_steps": image_request.steps,
            "model_path": image_request.model_path,
            "version": image_request.version,
            "scheduler_name": image_request.scheduler,
            "strength": image_request.strength,
            "loaded_lora": [],
            "loaded_embeddings": [],
            "controlnet_enabled": bool(image_request.controlnet_enabled),
            "is_txt2img": generator_section is GeneratorSection.TXT2IMG,
            "is_img2img": generator_section is GeneratorSection.IMG2IMG,
            "is_inpaint": generator_section is GeneratorSection.INPAINT,
            "is_outpaint": generator_section is GeneratorSection.OUTPAINT,
            "mask_blur": image_request.outpaint_mask_blur,
            "memory_settings_flags": {},
            "application_settings": self.application_settings,
            "path_settings": self.path_settings,
            "metadata_settings": self.metadata_settings,
            "controlnet_settings": self.controlnet_settings,
        }
