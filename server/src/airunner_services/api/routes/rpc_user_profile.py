"""RPC handlers: user profile image upload."""

from __future__ import annotations

import base64
import logging
from typing import Any

from airunner_services.api.routes.events import (
    _rpc_error_response,
    _rpc_register,
)

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB
ALLOWED_TYPES = {"avatar", "banner"}

# Magic bytes for supported image formats
_MAGIC_SIGNATURES: dict[bytes, str] = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpeg",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp",  # RIFF....WEBP
}


def _image_type(data: bytes) -> str | None:
    """Identify image format from magic bytes."""
    for magic, fmt in _MAGIC_SIGNATURES.items():
        if data.startswith(magic):
            if fmt == "webp" and data[8:12] != b"WEBP":
                continue
            return fmt
    return None


def _decode_image(b64: str) -> tuple[bytes | None, str | None]:
    """Decode a base64 data URL or raw base64 string.

    Returns ``(image_bytes, error)`` — exactly one is not None.
    """
    raw = b64.strip()
    # Strip data URL prefix if present
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(raw)
    except Exception:
        return None, "Invalid base64 encoding"
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return None, (
            f"Image too large (max {MAX_IMAGE_BYTES // (1024*1024)} MB)"
        )
    img_type = _image_type(image_bytes)
    if img_type not in ("png", "jpeg", "gif", "webp"):
        return None, f"Unsupported image type: {img_type or 'unknown'}"
    return image_bytes, None


# ── RPC Handler ──────────────────────────────────────────────────────────

@_rpc_register("POST", "/api/v1/user/profile-image")
async def _rpc_upload_profile_image(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Upload a profile avatar or banner image as base64.

    Expects ``{"type": "avatar"|"banner", "image": "<base64>"}``.
    """
    try:
        # ── Resolve authenticated user ──
        ws = kw.get("ws")
        if ws is None:
            return {"status": 400, "body": {"error": "WebSocket required"}}
        from airunner_services.api.ws_tenant import resolve_ws_tenant
        _tenant, account_id = resolve_ws_tenant(ws)
        if account_id is None:
            return {"status": 401, "body": {"error": "Authentication required"}}

        # ── Validate input ──
        image_type = body.get("type", "").strip()
        if image_type not in ALLOWED_TYPES:
            return {
                "status": 400,
                "body": {"error": f"type must be one of: {', '.join(sorted(ALLOWED_TYPES))}"},
            }
        image_b64 = body.get("image", "").strip()
        if not image_b64:
            return {"status": 400, "body": {"error": "image is required"}}
        image_bytes, err = _decode_image(image_b64)
        if err:
            return {"status": 400, "body": {"error": err}}
        assert image_bytes is not None  # guarded by err check above

        # ── Re-encode as clean base64 for storage ──
        stored_b64 = base64.b64encode(image_bytes).decode("ascii")

        # ── Store in DB ──
        from airunner_services.database.models.user import User
        user = User.objects.get(account_id)
        if user is None:
            return {"status": 404, "body": {"error": "User not found"}}
        column = f"{image_type}_image"
        User.objects.update(account_id, **{column: stored_b64})

        return {
            "status": 200,
            "body": {column: stored_b64},
        }

    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="profile image upload error",
        )
