"""Tests for per-tenant image scoping.

Part 2 (HIGH) — Generated images must be scoped per account so
user A cannot enumerate or download user B's images.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from airunner_services.api.routes.rpc_images import (
    _account_images_root,
    _resolve_account_id,
)


class TestAccountImagesRoot:
    """``_account_images_root`` isolates images per account."""

    def test_different_accounts_have_different_roots(self) -> None:
        """Account 1 and account 2 resolve to different directories."""
        root_1 = _account_images_root(1)
        root_2 = _account_images_root(2)
        assert root_1 != root_2
        assert str(root_1).endswith("/1")
        assert str(root_2).endswith("/2")

    def test_account_root_contains_account_id(self) -> None:
        """The account ID appears in the resolved path."""
        root = _account_images_root(42)
        assert "42" in root.parts


class TestResolveAccountId:
    """``_resolve_account_id`` extracts the account ID from RPC args."""

    def test_returns_none_when_no_ws(self) -> None:
        """No WebSocket in kwargs → None."""
        assert _resolve_account_id({}) is None

    @patch(
        "airunner_services.api.ws_tenant.resolve_ws_tenant",
    )
    def test_returns_account_id_from_ws(
        self, mock_resolve: MagicMock,
    ) -> None:
        """Returns the account_id resolved from the WebSocket."""
        mock_resolve.return_value = ("tenant_ab12_user", 7)
        ws = MagicMock()
        result = _resolve_account_id({"ws": ws})
        assert result == 7
        mock_resolve.assert_called_once_with(ws)

    @patch(
        "airunner_services.api.ws_tenant.resolve_ws_tenant",
    )
    def test_returns_none_for_unauthenticated_ws(
        self, mock_resolve: MagicMock,
    ) -> None:
        """Returns None when resolve_ws_tenant yields no account."""
        mock_resolve.return_value = (None, None)
        ws = MagicMock()
        result = _resolve_account_id({"ws": ws})
        assert result is None


class TestImagesPathSafety:
    """Existing path-safety validators are not bypassed."""

    def test_account_root_is_within_expected_base(self) -> None:
        """The per-account root stays under airunner base path."""
        from airunner_services.settings import AIRUNNER_BASE_PATH

        root = _account_images_root(123)
        base = Path(AIRUNNER_BASE_PATH)
        root.resolve().relative_to(base.resolve())
