"""Tests for WS-RPC image path validation.

Part 2 (MEDIUM-HIGH) — Security audit round 6.
The WS-RPC image handlers (_rpc_images_info, _rpc_images_delete,
_rpc_images_full, _rpc_images_thumb) must validate date and filename
path components the same way the HTTP endpoints do, rejecting ``..``
and other traversal sequences.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from airunner_services.api.routes.rpc_images import (
    _validate_rpc_path_params,
)


# ------------------------------------------------------------------ tests


class TestValidateRpcPathParams:
    """``_validate_rpc_path_params`` rejects unsafe components."""

    def test_valid_date_and_filename_pass(self) -> None:
        """Normal YYYYMMDD date + safe filename → None (valid)."""
        result = _validate_rpc_path_params(
            {"date": "20260101", "filename": "image.png"}
        )
        assert result is None

    def test_date_with_dotdot_rejected(self) -> None:
        """``date=".."`` is not 8 digits → rejected with 422."""
        result = _validate_rpc_path_params(
            {"date": "..", "filename": "image.png"}
        )
        assert result is not None
        assert result["status"] == 422

    def test_filename_with_dotdot_rejected(self) -> None:
        """``filename=".."`` → rejected with 422."""
        result = _validate_rpc_path_params(
            {"date": "20260101", "filename": ".."}
        )
        assert result is not None
        assert result["status"] == 422

    def test_filename_with_slash_rejected(self) -> None:
        """``filename`` containing ``/`` → rejected with 422."""
        result = _validate_rpc_path_params(
            {"date": "20260101", "filename": "subdir/image.png"}
        )
        assert result is not None
        assert result["status"] == 422

    def test_filename_with_backslash_rejected(self) -> None:
        """``filename`` containing ``\\`` → rejected with 422."""
        result = _validate_rpc_path_params(
            {"date": "20260101", "filename": "subdir\\image.png"}
        )
        assert result is not None
        assert result["status"] == 422

    def test_filename_with_null_byte_rejected(self) -> None:
        """``filename`` containing null byte → rejected with 422."""
        result = _validate_rpc_path_params(
            {"date": "20260101", "filename": "image\x00.png"}
        )
        assert result is not None
        assert result["status"] == 422

    def test_date_too_short_rejected(self) -> None:
        """Date shorter than 8 chars → rejected with 422."""
        result = _validate_rpc_path_params(
            {"date": "2026", "filename": "image.png"}
        )
        assert result is not None
        assert result["status"] == 422

    def test_date_not_digits_rejected(self) -> None:
        """Date with non-digit characters → rejected with 422."""
        result = _validate_rpc_path_params(
            {"date": "abcd0101", "filename": "image.png"}
        )
        assert result is not None
        assert result["status"] == 422

    def test_empty_date_rejected(self) -> None:
        """Empty date string → rejected with 422."""
        result = _validate_rpc_path_params(
            {"date": "", "filename": "image.png"}
        )
        assert result is not None
        assert result["status"] == 422

    def test_empty_filename_rejected(self) -> None:
        """Empty filename → rejected with 422."""
        result = _validate_rpc_path_params(
            {"date": "20260101", "filename": ""}
        )
        assert result is not None
        assert result["status"] == 422


# ------------------------------------------------------------------ handler tests


class TestRpcImagesInfoValidation:
    """``_rpc_images_info`` validates path params before path join."""

    @patch(
        "airunner_services.api.routes.rpc_images._resolve_account_id",
        return_value=1,
    )
    @patch(
        "airunner_services.api.routes.rpc_images._account_images_root",
    )
    def test_traversal_date_rejected(
        self,
        mock_root: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """date=".." → 422 before any filesystem access."""
        from airunner_services.api.routes.rpc_images import (
            _rpc_images_info,
        )
        import asyncio

        result = asyncio.run(
            _rpc_images_info(
                {},
                ws=MagicMock(),
                path_params={"date": "..", "filename": "ok.png"},
            )
        )
        assert result["status"] == 422
        # _account_images_root must NOT be called — we reject before
        # reaching the path join.
        mock_root.assert_not_called()

    @patch(
        "airunner_services.api.routes.rpc_images._resolve_account_id",
        return_value=1,
    )
    @patch(
        "airunner_services.api.routes.rpc_images._account_images_root",
    )
    def test_traversal_filename_rejected(
        self,
        mock_root: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """filename=".." → 422 before any filesystem access."""
        from airunner_services.api.routes.rpc_images import (
            _rpc_images_info,
        )
        import asyncio

        result = asyncio.run(
            _rpc_images_info(
                {},
                ws=MagicMock(),
                path_params={"date": "20260101", "filename": ".."},
            )
        )
        assert result["status"] == 422
        mock_root.assert_not_called()


class TestRpcImagesDeleteValidation:
    """``_rpc_images_delete`` validates path params before unlink."""

    @patch(
        "airunner_services.api.routes.rpc_images._resolve_account_id",
        return_value=1,
    )
    def test_traversal_date_rejected(self, mock_resolve: MagicMock) -> None:
        """date=".." → 422, no file is deleted."""
        from airunner_services.api.routes.rpc_images import (
            _rpc_images_delete,
        )
        import asyncio

        result = asyncio.run(
            _rpc_images_delete(
                {},
                ws=MagicMock(),
                path_params={"date": "..", "filename": "ok.png"},
            )
        )
        assert result["status"] == 422


class TestRpcImagesFullValidation:
    """``_rpc_images_full`` validates path params before file read."""

    @patch(
        "airunner_services.api.routes.rpc_images._resolve_account_id",
        return_value=1,
    )
    def test_traversal_filename_rejected(self, mock_resolve: MagicMock) -> None:
        """filename=".." → 422, no file bytes are served."""
        from airunner_services.api.routes.rpc_images import (
            _rpc_images_full,
        )
        import asyncio

        result = asyncio.run(
            _rpc_images_full(
                {},
                ws=MagicMock(),
                path_params={"date": "20260101", "filename": ".."},
            )
        )
        assert result["status"] == 422


class TestRpcImagesThumbValidation:
    """``_rpc_images_thumb`` validates path params before thumbnail gen."""

    @patch(
        "airunner_services.api.routes.rpc_images._resolve_account_id",
        return_value=1,
    )
    def test_traversal_date_rejected(self, mock_resolve: MagicMock) -> None:
        """date=".." → 422, no thumbnail is generated."""
        from airunner_services.api.routes.rpc_images import (
            _rpc_images_thumb,
        )
        import asyncio

        result = asyncio.run(
            _rpc_images_thumb(
                {},
                ws=MagicMock(),
                path_params={"date": "..", "filename": "ok.png"},
            )
        )
        assert result["status"] == 422
