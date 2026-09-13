"""RPC handlers: art images.

All image paths are scoped to the authenticated account so that one
account cannot enumerate or download another account's generated
images.  Date and filename path components are validated against the
same rules as the HTTP endpoints (see :mod:`image_validation`) so
that ``..`` segments cannot escape the per-account directory.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image as PILImage

from airunner_services.api.routes.events import (
    _rpc_error_response,
    _rpc_register,
)
from airunner_services.api.routes.image_validation import (
    validate_date_component,
    validate_filename_component,
)
from airunner_services.settings import AIRUNNER_BASE_PATH

logger = logging.getLogger(__name__)

# -- shared validation helpers ---------------------------------------------


def _validate_rpc_path_params(pp: dict) -> dict[str, Any] | None:
    """Validate *date* and *filename* from RPC path params.

    Returns ``None`` when both components are valid; returns an RPC
    error dict (status 422) when either is rejected.
    """
    date, filename = pp.get("date", ""), pp.get("filename", "")
    try:
        validate_date_component(date)
    except ValueError as exc:
        return {"status": 422, "body": {"error": str(exc)}}
    try:
        validate_filename_component(filename)
    except ValueError as exc:
        return {"status": 422, "body": {"error": str(exc)}}
    return None


def _resolve_account_id(kw: dict) -> int | None:
    """Return the authenticated account ID from RPC keyword args.

    RPC handlers receive the WebSocket object via ``kw["ws"]``.
    The token is re-decoded on every call (mirroring
    :func:`resolve_ws_tenant`) so a token revocation mid-connection
    is honoured.
    """
    ws = kw.get("ws")
    if ws is None:
        return None
    from airunner_services.api.ws_tenant import resolve_ws_tenant

    _tenant, account_id = resolve_ws_tenant(ws)
    return account_id


def _account_images_root(account_id: int) -> Path:
    """Return the per-account images root directory."""
    return (
        Path(AIRUNNER_BASE_PATH)
        / "art"
        / "other"
        / "images"
        / str(account_id)
    )


@_rpc_register("GET", "/api/v1/art/images/dates")
async def _rpc_images_dates(body: dict, **kw: Any) -> dict[str, Any]:
    """List image date directories for the authenticated account."""
    account_id = _resolve_account_id(kw)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    root = _account_images_root(account_id)
    dates: list[dict[str, str]] = []
    if root.is_dir():
        for d in sorted(root.iterdir(), reverse=True):
            if d.is_dir() and d.name.isdigit() and len(d.name) == 8:
                label = f"{d.name[:4]}-{d.name[4:6]}-{d.name[6:8]}"
                dates.append({"value": d.name, "label": label})
    return {"status": 200, "body": {"dates": dates}}


@_rpc_register("GET", "/api/v1/art/images/{date}")
async def _rpc_images_list(body: dict, **kw: Any) -> dict[str, Any]:
    """List images for a date (scoped to authenticated account)."""
    from airunner_services.api.routes.images import (
        _extract_metadata,
        _list_image_files,
    )

    account_id = _resolve_account_id(kw)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    pp: dict = kw.get("path_params", {})
    date = pp.get("date", "")
    # _rpc_images_list already performs its own date validation inline;
    # keep it as-is for backward compatibility — it is stricter
    # (requires 8 digits) than the shared validator but equivalent.
    if not date.isdigit() or len(date) != 8:
        return {"status": 422, "body": {"error": "Invalid date"}}
    root = _account_images_root(account_id) / date
    if not root.is_dir():
        return {"status": 200, "body": {"total": 0, "images": []}}
    files = _list_image_files(root)
    offset = int(body.get("offset", 0))
    limit_val = int(body.get("limit", 20))
    page = files[offset : offset + limit_val]
    images = []
    for p in page:
        meta = _extract_metadata(p) if p.suffix.lower() == ".png" else None
        try:
            st = p.stat()
            fsize, ftm = st.st_size, st.st_mtime
        except OSError:
            fsize, ftm = 0, 0.0
        images.append(
            {
                "id": p.name,
                "file_path": str(p),
                "file_size": fsize,
                "file_timestamp": ftm,
                "metadata": meta,
                "image_url": f"/api/v1/art/images/{date}/full/{p.name}",
                "thumbnail_url": (
                    f"/api/v1/art/images/{date}/thumb/{p.name}"
                ),
            }
        )
    return {"status": 200, "body": {"total": len(files), "images": images}}


@_rpc_register("GET", "/api/v1/art/images/{date}/info/{filename}")
async def _rpc_images_info(body: dict, **kw: Any) -> dict[str, Any]:
    """Get image info (scoped to authenticated account)."""
    from airunner_services.api.routes.images import _extract_metadata

    account_id = _resolve_account_id(kw)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    pp: dict = kw.get("path_params", {})
    err = _validate_rpc_path_params(pp)
    if err is not None:
        return err
    date, filename = pp["date"], pp["filename"]
    source = _account_images_root(account_id) / date / filename
    if not source.is_file():
        return {"status": 404, "body": {"error": "Not found"}}
    meta = (
        _extract_metadata(source) if source.suffix.lower() == ".png" else None
    )
    try:
        fsize = source.stat().st_size
    except OSError:
        fsize = 0
    return {
        "status": 200,
        "body": {
            "id": source.name,
            "file_path": str(source),
            "file_size": fsize,
            "metadata": meta,
            "image_url": f"/api/v1/art/images/{date}/full/{source.name}",
            "thumbnail_url": (
                f"/api/v1/art/images/{date}/thumb/{source.name}"
            ),
        },
    }


@_rpc_register("DELETE", "/api/v1/art/images/{date}/delete/{filename}")
async def _rpc_images_delete(body: dict, **kw: Any) -> dict[str, Any]:
    """Delete an image (scoped to authenticated account)."""
    account_id = _resolve_account_id(kw)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    pp: dict = kw.get("path_params", {})
    err = _validate_rpc_path_params(pp)
    if err is not None:
        return err
    date, filename = pp["date"], pp["filename"]
    source = _account_images_root(account_id) / date / filename
    if not source.is_file():
        return {"status": 404, "body": {"error": "Not found"}}
    try:
        source.unlink()
        return {
            "status": 200,
            "body": {"success": True, "deleted": filename},
        }
    except OSError as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="image delete failed",
        )


@_rpc_register("GET", "/api/v1/art/images/{date}/full/{filename}")
async def _rpc_images_full(body: dict, **kw: Any) -> dict[str, Any]:
    """Serve full image as binary (scoped to authenticated account)."""
    account_id = _resolve_account_id(kw)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    pp: dict = kw.get("path_params", {})
    err = _validate_rpc_path_params(pp)
    if err is not None:
        return err
    date, filename = pp["date"], pp["filename"]
    source = _account_images_root(account_id) / date / filename
    if not source.is_file():
        return {"status": 404, "body": {"error": "Not found"}}
    try:
        data = source.read_bytes()
        return {
            "status": 200,
            "binary": True,
            "headers": {"Content-Type": "image/png"},
            "body": data,
        }
    except OSError as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="image full read failed",
        )


@_rpc_register("GET", "/api/v1/art/images/{date}/thumb/{filename}")
async def _rpc_images_thumb(body: dict, **kw: Any) -> dict[str, Any]:
    """Serve thumbnail as binary (scoped to authenticated account)."""
    account_id = _resolve_account_id(kw)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    pp: dict = kw.get("path_params", {})
    err = _validate_rpc_path_params(pp)
    if err is not None:
        return err
    date, filename = pp["date"], pp["filename"]
    source = _account_images_root(account_id) / date / filename
    if not source.is_file():
        return {"status": 404, "body": {"error": "Not found"}}
    try:
        img = PILImage.open(source)
        img.thumbnail((200, 200))
        buf = BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        return {
            "status": 200,
            "binary": True,
            "headers": {"Content-Type": "image/png"},
            "body": data,
        }
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="image thumb read failed",
        )
