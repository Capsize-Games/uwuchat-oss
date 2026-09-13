"""Image generation request."""

from typing import Optional

from pydantic import BaseModel


class GenerationRequest(BaseModel):
    """Image generation request."""

    prompt: str
    negative_prompt: Optional[str] = ""
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg_scale: float = 7.5
    seed: Optional[int] = None
    num_images: int = 1
    model: Optional[str] = None
    version: Optional[str] = None
    scheduler: Optional[str] = None
    pipeline: Optional[str] = None
    strength: Optional[float] = None
    image_b64: Optional[str] = None
    mask_image_b64: Optional[str] = None
    skip_auto_export: bool = False
