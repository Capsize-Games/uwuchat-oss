"""Unit tests for the code-credits RPC handlers.

Mirrors test_rpc_code_mode.py's approach: the client's request()
helper always goes over the WS RPC channel, so
code_credits_rpc.py — not the FastAPI HTTP router in
code_credits_routes.py — is what an admin credits UI would actually
reach. See wiki/WebSocket-RPC.md gotcha #4: this exact bug (an admin
had no way to top up code credits through the app) is what these
handlers fix.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from projects.uwuchat.server.routes import code_credits_rpc as m

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


class TestGetCodeCredits:
    async def test_unauthenticated_returns_403(self, fake_ws) -> None:
        with _patch_resolve(None):
            result = await m._rpc_get_code_credits(
                {}, ws=fake_ws, path_params={"account_id": "1"},
            )
        assert result["status"] == 403

    async def test_non_superuser_returns_403(self, fake_ws) -> None:
        with _patch_resolve(5), _patch_account(False):
            result = await m._rpc_get_code_credits(
                {}, ws=fake_ws, path_params={"account_id": "1"},
            )
        assert result["status"] == 403

    async def test_invalid_account_id_returns_400(self, fake_ws) -> None:
        with _patch_resolve(5), _patch_account(True):
            result = await m._rpc_get_code_credits(
                {}, ws=fake_ws, path_params={"account_id": "nope"},
            )
        assert result["status"] == 400

    async def test_returns_balance_and_transactions(self, fake_ws) -> None:
        query = MagicMock()
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        query.all.return_value = []
        session = MagicMock()
        session.query.return_value = query
        session_scope = MagicMock()
        session_scope.__enter__.return_value = session
        session_scope.__exit__.return_value = False
        with _patch_resolve(5), _patch_account(True), patch(
            "projects.uwuchat.server.routes.code_credits_rpc"
            ".remaining_budget_usd",
            return_value=Decimal("5.0000"),
        ), patch(
            "projects.uwuchat.server.routes.code_credits_rpc"
            ".public_session_scope",
            return_value=session_scope,
        ):
            result = await m._rpc_get_code_credits(
                {}, ws=fake_ws, path_params={"account_id": "1"},
            )
        assert result["status"] == 200
        assert result["body"]["balance_usd"] == "5.0000"
        assert result["body"]["recent_transactions"] == []


class TestTopUpCodeCredits:
    async def test_unauthenticated_returns_403(self, fake_ws) -> None:
        with _patch_resolve(None):
            result = await m._rpc_top_up_code_credits(
                {"amount_usd": "5.00"},
                ws=fake_ws,
                path_params={"account_id": "1"},
            )
        assert result["status"] == 403

    async def test_non_positive_amount_returns_400(self, fake_ws) -> None:
        with _patch_resolve(5), _patch_account(True):
            for bad in ("0", "-5", "0.0000"):
                result = await m._rpc_top_up_code_credits(
                    {"amount_usd": bad},
                    ws=fake_ws,
                    path_params={"account_id": "1"},
                )
                assert result["status"] == 400, bad

    async def test_non_decimal_amount_returns_400(self, fake_ws) -> None:
        with _patch_resolve(5), _patch_account(True):
            result = await m._rpc_top_up_code_credits(
                {"amount_usd": "not-a-number"},
                ws=fake_ws,
                path_params={"account_id": "1"},
            )
        assert result["status"] == 400

    async def test_valid_topup_returns_new_balance(self, fake_ws) -> None:
        with _patch_resolve(5), _patch_account(True), patch(
            "projects.uwuchat.server.routes.code_credits_rpc"
            ".add_credits",
            return_value=Decimal("25.5000"),
        ) as mock_add:
            result = await m._rpc_top_up_code_credits(
                {"amount_usd": "25.50", "note": "manual top-up"},
                ws=fake_ws,
                path_params={"account_id": "1"},
            )
        assert result["status"] == 200
        assert result["body"]["balance_usd"] == "25.5000"
        mock_add.assert_called_once_with(
            1, Decimal("25.50"), note="manual top-up",
        )
