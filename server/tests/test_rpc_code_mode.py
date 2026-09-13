"""Unit tests for the code-mode RPC handlers.

The client's ``request()`` helper always goes over the WS RPC channel
(see ``routes/__init__.py``'s "WebSocket-only architecture" docstring),
so ``rpc_code_mode.py`` — not the FastAPI HTTP router in
``code_mode_routes.py`` — is what the client actually reaches. These
tests cover the four outcomes a UI toggle click can hit: unauthenticated,
non-superuser, someone else's conversation, and a real owned toggle.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from airunner_services.api.routes import rpc_code_mode as m

pytestmark = pytest.mark.asyncio


@pytest.fixture
def fake_ws():
    return MagicMock(name="websocket")


def _patch_resolve(account_id):
    return patch(
        "airunner_services.api.ws_tenant.resolve_ws_tenant",
        return_value=("tenant_x", account_id),
    )


def _patch_account(is_superuser):
    acct = MagicMock()
    acct.is_superuser = is_superuser
    return patch(
        "extensions.auth.server.models.Account.objects.get",
        return_value=acct,
    )


class TestCodeModeGetAuth:
    async def test_unauthenticated_returns_403(self, fake_ws) -> None:
        with _patch_resolve(None):
            result = await m._rpc_code_mode_get({}, ws=fake_ws)
        assert result["status"] == 403

    async def test_non_superuser_returns_403(self, fake_ws) -> None:
        with _patch_resolve(5), _patch_account(False):
            result = await m._rpc_code_mode_get({}, ws=fake_ws)
        assert result["status"] == 403

    async def test_invalid_conversation_id_returns_400(self, fake_ws) -> None:
        with _patch_resolve(5), _patch_account(True):
            result = await m._rpc_code_mode_get(
                {}, ws=fake_ws, path_params={"conversation_id": "nope"}
            )
        assert result["status"] == 400


class TestCodeModeGetOwnership:
    async def test_other_users_conversation_returns_404(
        self, fake_ws
    ) -> None:
        other_conv = MagicMock(user_id=999)
        with _patch_resolve(5), _patch_account(True), patch(
            "airunner_services.database.models.conversation.Conversation"
            ".objects.get",
            return_value=other_conv,
        ):
            result = await m._rpc_code_mode_get(
                {}, ws=fake_ws, path_params={"conversation_id": "1"}
            )
        assert result["status"] == 404

    async def test_owned_conversation_returns_enabled_state(
        self, fake_ws
    ) -> None:
        own_conv = MagicMock(user_id=5, user_data={"code_mode": True})
        with _patch_resolve(5), _patch_account(True), patch(
            "airunner_services.database.models.conversation.Conversation"
            ".objects.get",
            return_value=own_conv,
        ):
            result = await m._rpc_code_mode_get(
                {}, ws=fake_ws, path_params={"conversation_id": "1"}
            )
        assert result["status"] == 200
        assert result["body"] == {"enabled": True, "mode": "code"}


class TestCodeModeSet:
    async def test_unauthenticated_returns_403(self, fake_ws) -> None:
        with _patch_resolve(None):
            result = await m._rpc_code_mode_set(
                {"enabled": True},
                ws=fake_ws,
                path_params={"conversation_id": "1"},
            )
        assert result["status"] == 403

    async def test_owned_conversation_toggles_and_returns_state(
        self, fake_ws
    ) -> None:
        own_conv = MagicMock(user_id=5, user_data={})
        with _patch_resolve(5), _patch_account(True), patch(
            "airunner_services.database.models.conversation.Conversation"
            ".objects.get",
            return_value=own_conv,
        ), patch(
            "airunner_services.database.models.conversation.Conversation"
            ".objects.update"
        ) as mock_update:
            result = await m._rpc_code_mode_set(
                {"enabled": True},
                ws=fake_ws,
                path_params={"conversation_id": "1"},
            )
        assert result["status"] == 200
        assert result["body"] == {"enabled": True, "mode": "code"}
        mock_update.assert_called_once()

    async def test_set_with_mode_persists_slug(self, fake_ws) -> None:
        own_conv = MagicMock(user_id=5, user_data={})
        with _patch_resolve(5), _patch_account(True), patch(
            "airunner_services.database.models.conversation.Conversation"
            ".objects.get",
            return_value=own_conv,
        ), patch(
            "airunner_services.database.models.conversation.Conversation"
            ".objects.update"
        ):
            result = await m._rpc_code_mode_set(
                {"enabled": True, "mode": "architect"},
                ws=fake_ws,
                path_params={"conversation_id": "1"},
            )
        assert result["status"] == 200
        assert result["body"] == {"enabled": True, "mode": "architect"}

    async def test_set_with_unknown_mode_returns_400(self, fake_ws) -> None:
        own_conv = MagicMock(user_id=5, user_data={})
        with _patch_resolve(5), _patch_account(True), patch(
            "airunner_services.database.models.conversation.Conversation"
            ".objects.get",
            return_value=own_conv,
        ):
            result = await m._rpc_code_mode_set(
                {"enabled": True, "mode": "nonsense"},
                ws=fake_ws,
                path_params={"conversation_id": "1"},
            )
        assert result["status"] == 400
