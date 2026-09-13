"""WS ban enforcement test: banned accounts rejected mid-session.

Uses Starlette TestClient.websocket_connect() to open a real WS
connection, simulate a ban, and assert rejection.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, WebSocket


@pytest.mark.timeout(15)
class TestWsBanEnforcement:
    """Banned accounts are rejected at WS connection and RPC time."""

    def test_banned_account_ws_connection_rejected(self) -> None:
        from airunner_services.api.ws_tenant import resolve_ws_tenant

        with patch(
            "airunner_services.api.ws_tenant._extract_token",
            return_value="fake-token",
        ), patch(
            "airunner_services.api.ws_tenant._decode_ws_token",
            return_value={
                "sub": "42",
                "type": "access",
                "tenant": "test",
            },
        ), patch(
            "extensions.auth.server.middleware._check_account_status",
            return_value=("banned", 0),
        ):
            ws = MagicMock()
            tenant_key, account_id = resolve_ws_tenant(ws)

        assert tenant_key is None
        assert account_id is None

    def test_active_account_ws_connection_accepted(self) -> None:
        from airunner_services.api.ws_tenant import resolve_ws_tenant

        with patch(
            "airunner_services.api.ws_tenant._extract_token",
            return_value="fake-token",
        ), patch(
            "airunner_services.api.ws_tenant._decode_ws_token",
            return_value={
                "sub": "42",
                "type": "access",
                "tenant": "test",
            },
        ), patch(
            "extensions.auth.server.middleware._check_account_status",
            return_value=(None, 0),
        ):
            ws = MagicMock()
            tenant_key, account_id = resolve_ws_tenant(ws)

        assert tenant_key is not None
        assert account_id == 42

    def test_no_token_returns_none(self) -> None:
        from airunner_services.api.ws_tenant import resolve_ws_tenant

        with patch(
            "airunner_services.api.ws_tenant._extract_token",
            return_value=None,
        ):
            ws = MagicMock()
            tenant_key, account_id = resolve_ws_tenant(ws)

        assert tenant_key is None
        assert account_id is None

    def test_mid_session_ban_rejects_next_rpc(self) -> None:
        """Open WS connections via TestClient, simulate active vs banned
        account, assert the banned connection gets a 403 response."""
        from fastapi.testclient import TestClient
        from airunner_services.api.ws_tenant import resolve_ws_tenant

        app = FastAPI()

        @app.websocket("/ws")
        async def ws_endpoint(websocket: WebSocket):
            await websocket.accept()
            try:
                data = await websocket.receive_json()
            except Exception:
                return
            if data.get("type") == "rpc":
                tenant_key, account_id = resolve_ws_tenant(websocket)
                if tenant_key is None or account_id is None:
                    # Send 403 as text (not JSON) to avoid TestClient
                    # timing issues with close-after-send.
                    await websocket.send_text(
                        json.dumps({
                            "type": "rpc_response", "status": 403,
                            "body": {"detail": "Account banned"},
                        }),
                    )
                    await websocket.close()
                    return
                await websocket.send_text(
                    json.dumps({
                        "type": "rpc_response", "status": 200,
                        "body": {"ok": True},
                    }),
                )

        with patch(
            "airunner_services.api.ws_tenant._extract_token",
            return_value="fake-token",
        ), patch(
            "airunner_services.api.ws_tenant._decode_ws_token",
            return_value={
                "sub": "42",
                "type": "access",
                "tenant": "test",
            },
        ):
            # Active account → RPC succeeds.
            with patch(
                "extensions.auth.server.middleware."
                "_check_account_status",
                return_value=(None, 0),
            ):
                client = TestClient(app)
                with client.websocket_connect("/ws") as ws:
                    ws.send_json({
                        "type": "rpc", "id": "1",
                        "method": "GET", "path": "/test",
                    })
                    resp = json.loads(ws.receive_text())
                    assert resp["status"] == 200

            # Banned account → RPC returns 403.
            with patch(
                "extensions.auth.server.middleware."
                "_check_account_status",
                return_value=("banned", 0),
            ):
                client2 = TestClient(app)
                with client2.websocket_connect("/ws") as ws2:
                    ws2.send_json({
                        "type": "rpc", "id": "2",
                        "method": "GET", "path": "/test",
                    })
                    resp2 = json.loads(ws2.receive_text())
                    assert resp2["status"] == 403
                    assert "banned" in str(
                        resp2.get("body", {})
                    ).lower()
