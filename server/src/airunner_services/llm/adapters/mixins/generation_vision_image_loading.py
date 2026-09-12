"""Image-loading helpers for vision generation inputs.

All remote-url loading now routes through the shared SSRF-safe fetch
layer (:mod:`airunner_services.url_safety`) and local filesystem loads
are confined to ``AIRUNNER_BASE_PATH`` via ``.resolve()`` containment
(matching the pattern already used by ``LocalStorageBackend._resolve``).
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any, Optional

from PIL import Image as PILImage


def image_from_data_url(path_str: str) -> PILImage.Image:
    """Decode one `data:image` URL into a PIL image."""
    try:
        base64_data = path_str.split(",", 1)[1]
    except IndexError:
        base64_data = path_str
    image_bytes = base64.b64decode(base64_data)
    return PILImage.open(io.BytesIO(image_bytes)).convert("RGB")


def image_from_remote_url(
    adapter: Any,
    path_str: str,
) -> Optional[PILImage.Image]:
    """Download and decode one remote image URL via the SSRF-safe fetch
    layer."""
    from airunner_services.url_safety import safe_fetch_bytes, SSRFBlocked

    try:
        data = safe_fetch_bytes(path_str, timeout_seconds=10)
        return PILImage.open(io.BytesIO(data)).convert("RGB")
    except SSRFBlocked:
        # SSRF rejection — silently skip; the adversarial URL must not
        # be reachable even for a blind outbound connection.
        return None
    except Exception as error:
        adapter.logger.error("Failed to download image: %s", error)
        return None


def image_from_file(
    adapter: Any,
    path_str: str,
) -> Optional[PILImage.Image]:
    """Load one image from a local file path confined to the airunner
    base directory.

    Absolute and relative paths are both resolved and then checked
    against ``AIRUNNER_BASE_PATH`` using ``Path.relative_to()`` so
    that ``..`` segments or symlinks cannot escape to read arbitrary
    filesystem files (LFI).
    """
    from airunner_services.settings import AIRUNNER_BASE_PATH

    fs_path = Path(path_str).expanduser()
    try:
        resolved = fs_path.resolve()
        base = Path(AIRUNNER_BASE_PATH).resolve()
        resolved.relative_to(base)
    except (ValueError, OSError):
        # Path does not resolve within the allowed base directory —
        # treat as nonexistent rather than surfacing the containment
        # failure to avoid leaking filesystem layout info.
        return None

    if not resolved.is_file():
        return None
    try:
        return PILImage.open(resolved).convert("RGB")
    except Exception as error:
        adapter.logger.error("Failed to open image file: %s", error)
        return None


def image_from_base64_string(path_str: str) -> Optional[PILImage.Image]:
    """Decode one raw base64 string into a PIL image when possible."""
    try:
        image_bytes = base64.b64decode(path_str)
        return PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None
