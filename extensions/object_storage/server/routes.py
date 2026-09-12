"""Object storage extension — upload & serve routes.

Mounted at ``/api/v1/object_storage``. All endpoints run after the auth
middleware, so the tenant context is already active; uploads are written to
``tenants/<schema>/...`` keys and registered in the caller's schema.

Endpoints:
  POST /documents              multipart upload → store + register Document
  GET  /documents/{id}/content stream a stored document's bytes
  POST /images                 multipart upload → store an image
  GET  /images/content?key=    stream (or redirect to) a stored image
"""

from __future__ import annotations

import mimetypes
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse, Response

from airunner_services.database.models.document import Document
from airunner_services.database.session import session_scope
from airunner_services.storage.backends import (
    get_storage_backend,
    tenant_storage_key,
)

router = APIRouter()

# Max upload size (bytes) — guards against unbounded memory reads.
_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MiB

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _require_auth():
    """Resolve the auth extension's require_auth dependency (lazy)."""
    try:
        from extensions.auth.server.dependencies import require_auth
    except Exception as exc:  # pragma: no cover - auth ext absent
        raise HTTPException(
            status_code=503, detail="Auth extension unavailable"
        ) from exc
    return require_auth


def _safe_filename(name: str) -> str:
    """Return a filesystem/-key-safe basename, never empty."""
    base = Path(name or "").name
    cleaned = _SAFE_NAME_RE.sub("_", base).strip("._") or "upload"
    return cleaned[:200]


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload too large")
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")
    return data


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    account_id: int = Depends(_require_auth()),
) -> dict[str, Any]:
    """Store an uploaded document and register it in the caller's tenant."""
    del account_id  # presence enforces auth; tenant comes from context
    data = await _read_upload(file)
    name = _safe_filename(file.filename or "document")
    key = tenant_storage_key("documents", f"{uuid.uuid4().hex}_{name}")

    content_type = file.content_type or (
        mimetypes.guess_type(name)[0] or "application/octet-stream"
    )
    get_storage_backend().save(key, data, content_type=content_type)

    with session_scope() as session:
        doc = Document(path=key, active=False, indexed=False)
        session.add(doc)
        session.flush()
        result = {
            "id": doc.id,
            "name": name,
            "path": key,
            "indexed": False,
            "active": False,
        }
    return result


@router.get("/documents/{doc_id}/content")
async def get_document_content(
    doc_id: int,
    account_id: int = Depends(_require_auth()),
) -> Response:
    """Stream the bytes of a stored document owned by the caller's tenant."""
    del account_id
    with session_scope() as session:
        doc = session.query(Document).filter(Document.id == doc_id).first()
        if doc is None or not doc.path:
            raise HTTPException(status_code=404, detail="Document not found")
        key = str(doc.path)

    backend = get_storage_backend()
    if not backend.exists(key):
        raise HTTPException(status_code=404, detail="Object not found")
    data = backend.open(key)
    media_type = (
        mimetypes.guess_type(key)[0] or "application/octet-stream"
    )
    return Response(content=data, media_type=media_type)


@router.post("/images")
async def upload_image(
    file: UploadFile = File(...),
    account_id: int = Depends(_require_auth()),
) -> dict[str, Any]:
    """Store an uploaded image under the caller's tenant prefix."""
    del account_id
    data = await _read_upload(file)
    name = _safe_filename(file.filename or "image.png")
    key = tenant_storage_key("images", f"{uuid.uuid4().hex}_{name}")
    content_type = file.content_type or (
        mimetypes.guess_type(name)[0] or "application/octet-stream"
    )
    get_storage_backend().save(key, data, content_type=content_type)
    backend = get_storage_backend()
    return {"key": key, "name": name, "url": backend.url(key)}


@router.get("/images/content")
async def get_image_content(
    key: str = Query(..., description="Tenant-scoped image storage key"),
    account_id: int = Depends(_require_auth()),
) -> Response:
    """Serve a stored image — redirect to a presigned URL when available."""
    del account_id
    backend = get_storage_backend()

    # Enforce tenant isolation via real path containment (not string prefix).
    # The key must resolve to a descendant of the caller's tenant-images
    # subtree, not merely start with that prefix as a string.  A naive
    # startswith() check survives ``..`` segments because
    # ``tenants/<me>/images/../../<you>/images/x`` still starts with
    # ``tenants/<me>/images`` as a literal string, even though it lexically
    # resolves to a different tenant's directory.
    _raise_forbidden_tenant_key(backend, key, "images")

    presigned = backend.url(key)
    if presigned:
        return RedirectResponse(url=presigned)
    if not backend.exists(key):
        raise HTTPException(status_code=404, detail="Object not found")
    data = backend.open(key)
    media_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return Response(content=data, media_type=media_type)


def _raise_forbidden_tenant_key(
    backend: Any,
    key: str,
    *subpath: str,
) -> None:
    """Validate that *key* is safely within the caller's tenant subtree.

    Resolves both the candidate key and the expected tenant-subtree prefix
    through the backend's own path resolution and then verifies the
    resolved candidate is a descendant of the resolved prefix using
    ``Path.relative_to()``.

    For backends that do not support filesystem-style path resolution
    (e.g. S3), the function delegates to a pure-string fallback that
    normalises ``..`` segments via :class:`PurePosixPath`.
    """
    expected_prefix = tenant_storage_key(*subpath)
    try:
        candidate_resolved = backend.resolve_path(key)
        prefix_resolved = backend.resolve_path(expected_prefix)
        candidate_resolved.relative_to(prefix_resolved)
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden key")
    except NotImplementedError:
        # Backend has no filesystem resolution — use PurePosixPath
        # normalisation which correctly collapses ``..`` segments
        # even when the storage layer treats keys as opaque.
        from pathlib import PurePosixPath

        candidate_norm = str(PurePosixPath(key))
        prefix_norm = str(PurePosixPath(expected_prefix))
        if not candidate_norm.startswith(prefix_norm + "/") and candidate_norm != prefix_norm:
            raise HTTPException(status_code=403, detail="Forbidden key")


__all__ = ["router"]
