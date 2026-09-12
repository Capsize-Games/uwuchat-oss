"""Art generation adapter wrapping the existing local art pipeline."""

from __future__ import annotations

import base64
from typing import Any, Optional
from uuid import uuid4

from airunner_services.shared.interfaces.art_interface import (
    ArtGenerationRequest,
    ArtGenerationResponse,
    ArtInferenceInterface,
)


class ArtGenerationAdapter(ArtInferenceInterface):
    """Bridge the existing local art pipeline into the shared interface.

    Delegates to :class:`LocalFallbackArtClient`, which owns the
    signal-based SDWorker dispatch path. ``ArtGenerationRequest`` fields
    are translated into ``ArtInvocationRequest`` metadata that
    ``LocalFallbackArtClient`` understands.
    """

    def __init__(self, timeout_seconds: Optional[float] = 300.0) -> None:
        self._client: Any = None
        self._timeout_seconds = timeout_seconds

    # ------------------------------------------------------------------
    # ArtInferenceInterface
    # ------------------------------------------------------------------

    def generate(
        self,
        request: ArtGenerationRequest,
        progress_callback: Any = None,
    ) -> ArtGenerationResponse:
        """Generate images through the existing local signal-based pipeline."""
        from airunner_services.ipc.messages import RequestEnvelope
        from airunner_services.runtimes.contracts import (
            ArtInvocationRequest,
            RuntimeAction,
            RuntimeKind,
        )

        client = self._client or self._build_client()
        invocation = ArtInvocationRequest(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            model=request.model or "",
            width=request.width,
            height=request.height,
            steps=request.steps,
            cfg_scale=request.cfg_scale,
            seed=request.seed or 42,
            num_images=request.num_images,
            metadata={
                "pipeline": request.pipeline,
                "version": request.version,
                "scheduler": request.scheduler,
                "strength": request.strength,
                "image_b64": request.init_image_b64,
                "mask_b64": request.mask_image_b64,
                "skip_auto_export": True,
            },
        )
        envelope = RequestEnvelope(
            request_id=str(uuid4()),
            runtime=RuntimeKind.ART,
            action=RuntimeAction.INVOKE,
            payload=invocation.model_dump(),
        )
        if progress_callback is not None:
            response = client.invoke_with_progress(envelope, progress_callback)
        else:
            response = client.invoke(envelope)

        images: list[bytes] = []
        if response.payload:
            for b64_img in response.payload.get("images", []):
                images.append(base64.b64decode(b64_img))

        return ArtGenerationResponse(
            images=images,
            seed=request.seed or 42,
            metadata={
                "pipeline": request.pipeline,
                "version": request.version,
                "status": (
                    response.status.value
                    if hasattr(response.status, "value")
                    else str(response.status)
                ),
            },
        )

    def cancel(self) -> None:
        if self._client is not None:
            self._client.cancel(str(uuid4()))

    @property
    def is_loaded(self) -> bool:
        return self._client is not None

    def load_model(self) -> None:
        self._build_client()

    def unload_model(self) -> None:
        self._client = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_client(self) -> Any:
        from airunner_services.runtimes.local_fallback import (
            LocalFallbackArtClient,
        )

        self._client = LocalFallbackArtClient(
            timeout_seconds=self._timeout_seconds,
        )
        return self._client
