"""Common interface for art/image generation — edge and cloud both satisfy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ArtGenerationRequest:
    """Portable request payload for one image generation.

    This dataclass is framework-agnostic — edge and cloud implementations
    translate it into their own internal request formats.
    """

    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg_scale: float = 7.0
    seed: Optional[int] = None
    num_images: int = 1
    model: Optional[str] = None
    version: Optional[str] = None
    scheduler: Optional[str] = None
    # img2img / inpaint
    init_image_b64: Optional[str] = None  # base64 PNG
    mask_image_b64: Optional[str] = None  # base64 PNG, white = inpaint
    strength: float = 0.75
    # pipeline
    pipeline: str = "txt2img"


@dataclass(frozen=True)
class ArtGenerationResponse:
    """Portable response payload from one image generation."""

    images: list[bytes]  # raw PNG bytes
    seed: int
    metadata: dict[str, Any]


class ArtInferenceInterface(ABC):
    """Abstract inference boundary for art / image generation.

    Every image-generation backend (local SDXL, local Z-Image, fal.ai,
    WaveSpeedAI, etc.) must satisfy this interface.
    """

    @abstractmethod
    def generate(
        self,
        request: ArtGenerationRequest,
        progress_callback: Any = None,
    ) -> ArtGenerationResponse:
        """Generate images from one request.

        Args:
            request: The portable generation request.
            progress_callback: Optional callback receiving
                ``(step: int, total: int)`` for progress reporting.

        Returns:
            An :class:`ArtGenerationResponse` with generated image bytes
            and metadata.
        """

    @abstractmethod
    def cancel(self) -> None:
        """Cancel the current generation on a best-effort basis."""

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Return whether the pipeline / model is ready."""

    @abstractmethod
    def load_model(self) -> None:
        """Prepare the pipeline for inference."""

    @abstractmethod
    def unload_model(self) -> None:
        """Release pipeline resources."""


__all__ = [
    "ArtGenerationRequest",
    "ArtGenerationResponse",
    "ArtInferenceInterface",
]
