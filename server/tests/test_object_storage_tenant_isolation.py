"""Tests for cross-tenant path traversal in object-storage image-serving.

Part 1 (HIGH) — Security audit round 6.
The ``get_image_content`` route must reject keys containing ``..``
segments that would resolve to a different tenant's directory, and
must allow legitimate same-tenant keys.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from airunner_services.storage.backends import LocalStorageBackend


# ------------------------------------------------------------------ helpers


def _fake_backend(root: Path) -> LocalStorageBackend:
    """Return a :class:`LocalStorageBackend` for testing."""
    return LocalStorageBackend(str(root))


def _make_prefix(schema: str, *parts: str) -> str:
    """Build a tenant-prefixed key for a specific schema."""
    cleaned = [p.strip("/") for p in parts if p and p.strip("/")]
    return "/".join(["tenants", schema, *cleaned])


# ------------------------------------------------------------------ tests


class TestRaiseForbiddenTenantKey:
    """``_raise_forbidden_tenant_key`` rejects traversal keys."""

    @pytest.fixture
    def backend(self, tmp_path: Path) -> LocalStorageBackend:
        return _fake_backend(tmp_path)

    @staticmethod
    def _call_check(backend, key: str, *subpath: str) -> None:
        """Call the private check helper directly."""
        from extensions.object_storage.server.routes import (
            _raise_forbidden_tenant_key,
        )

        with patch(
            "extensions.object_storage.server.routes.tenant_storage_key",
            return_value=_make_prefix("tenant_aaaa", *subpath),
        ):
            _raise_forbidden_tenant_key(backend, key, *subpath)

    def test_legitimate_same_tenant_key_passes(
        self, backend: LocalStorageBackend,
    ) -> None:
        """A key within the caller's tenant-images subtree is allowed."""
        key = "tenants/tenant_aaaa/images/some_image.png"
        # Should not raise.
        self._call_check(backend, key, "images")

    def test_traversal_to_other_tenant_rejected(
        self, backend: LocalStorageBackend,
    ) -> None:
        """A key with .. segments escaping to another tenant is rejected."""
        key = (
            "tenants/tenant_aaaa/images/../../tenant_bbbb/images/x.png"
        )
        with pytest.raises(HTTPException) as exc_info:
            self._call_check(backend, key, "images")
        assert exc_info.value.status_code == 403

    def test_traversal_outside_tenants_rejected(
        self, backend: LocalStorageBackend,
    ) -> None:
        """A key with enough .. to escape the tenants/ tree is rejected."""
        key = "tenants/tenant_aaaa/images/../../../etc/passwd"
        with pytest.raises(HTTPException) as exc_info:
            self._call_check(backend, key, "images")
        assert exc_info.value.status_code == 403

    def test_traversal_outside_images_subpath_rejected(
        self, backend: LocalStorageBackend,
    ) -> None:
        """A key that stays within the same tenant but escapes the
        ``images/`` subpath into ``documents/`` is rejected."""
        key = "tenants/tenant_aaaa/images/../documents/some_doc.pdf"
        with pytest.raises(HTTPException) as exc_info:
            self._call_check(backend, key, "images")
        assert exc_info.value.status_code == 403

    def test_empty_key_rejected(
        self, backend: LocalStorageBackend,
    ) -> None:
        """An empty key is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self._call_check(backend, "", "images")
        assert exc_info.value.status_code == 403

    def test_key_exactly_matching_prefix_allowed(
        self, backend: LocalStorageBackend,
    ) -> None:
        """A key that is exactly the tenant-images prefix (no trailing
        filename) is still contained and allowed."""
        key = "tenants/tenant_aaaa/images"
        self._call_check(backend, key, "images")


class TestGetImageContentRoute:
    """The ``/images/content`` endpoint uses the path-containment check."""

    def test_traversal_key_returns_403(self) -> None:
        """A client-supplied key with ``..`` traversal returns 403."""
        try:
            from extensions.object_storage.server.routes import (
                get_image_content,
            )
        except ImportError:
            pytest.skip("object_storage extension not available")

        with patch(
            "extensions.object_storage.server.routes._require_auth",
        ) as mock_auth, patch(
            "extensions.object_storage.server.routes.get_storage_backend",
        ) as mock_backend_factory, patch(
            "extensions.object_storage.server.routes.tenant_storage_key",
            return_value="tenants/tenant_aaaa/images",
        ):
            mock_auth.return_value = lambda: 1
            mock_backend = MagicMock()
            mock_backend.resolve_path.side_effect = lambda k: (
                Path("/tmp/storage") / k
            ).resolve()
            mock_backend_factory.return_value = mock_backend

            import asyncio

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(
                    get_image_content(
                        key="tenants/tenant_aaaa/images/../../"
                        "tenant_bbbb/images/x.png",
                        account_id=1,
                    )
                )
            assert exc_info.value.status_code == 403
