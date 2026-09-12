"""Auth-completeness regression tests for WS-RPC dispatch.

Part 15 (MEDIUM) — Verifies that every RPC message goes through
``check_rpc_rate`` (which unconditionally rejects unauthenticated
callers with ``account_id is None``) before reaching the handler.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestWsRpcAuthGate:
    """``_handle_rpc_message`` must call ``check_rpc_rate`` before
    dispatching to any handler."""

    @patch("airunner_services.api.routes.events._dispatch_rpc")
    @patch("airunner_services.api.routes.events.check_rpc_rate")
    @patch("airunner_services.api.routes.events._safe_send_json")
    async def test_check_rpc_rate_called_before_dispatch(
        self,
        mock_send: MagicMock,
        mock_check: MagicMock,
        mock_dispatch: MagicMock,
    ) -> None:
        """Authenticated caller: check_rpc_rate runs BEFORE dispatch.

        Uses a shared call-order list with side_effect to assert
        actual ordering — not just that both were called.
        """
        from airunner_services.api.routes.events import (
            _handle_rpc_message,
        )

        mock_dispatch.return_value = {"status": 200, "body": {}}

        call_order: list[str] = []
        mock_check.side_effect = (
            lambda *a, **k: call_order.append("check") or True
        )
        # _dispatch_rpc is awaited in the real code; side_effect
        # must return an awaitable (AsyncMock does this by default
        # when we patch with MagicMock — but we need the list append
        # BEFORE the await, so use a sync lambda that returns a
        # coroutine-return-value.  The real _dispatch_rpc is
        # async, but the mock doesn't need to be async — the caller
        # awaits whatever the mock returns.  We just need the side
        # effect to record the call before the await happens.
        async def _record_dispatch(*a, **k):
            call_order.append("dispatch")
            return {"status": 200, "body": {}}
        mock_dispatch.side_effect = _record_dispatch

        ws = MagicMock()
        raw = {"type": "rpc", "id": "req-1", "method": "GET",
               "path": "/api/v1/chatbots", "body": {}}

        await _handle_rpc_message(raw, ws, 42)

        assert call_order == ["check", "dispatch"], (
            f"Expected check before dispatch, got {call_order}"
        )

    @patch("airunner_services.api.routes.events._dispatch_rpc")
    @patch("airunner_services.api.routes.events.check_rpc_rate")
    @patch("airunner_services.api.routes.events._safe_send_json")
    async def test_rate_limited_caller_blocks_dispatch(
        self,
        mock_send: MagicMock,
        mock_check: MagicMock,
        mock_dispatch: MagicMock,
    ) -> None:
        """Rate-limited caller: 429 sent, dispatch NOT called."""
        from airunner_services.api.routes.events import (
            _handle_rpc_message,
        )

        mock_check.return_value = False

        ws = MagicMock()
        raw = {"type": "rpc", "id": "req-1", "method": "GET",
               "path": "/api/v1/chatbots", "body": {}}

        await _handle_rpc_message(raw, ws, 42)

        mock_check.assert_called_once_with(42)
        mock_dispatch.assert_not_called()
        mock_send.assert_called_once()
        sent_json = mock_send.call_args[0][1]
        assert sent_json["status"] == 429


class TestWsRpcUnauthenticated:
    """Unauthenticated callers must be rejected before dispatch."""

    @patch("airunner_services.api.routes.events._dispatch_rpc")
    @patch("airunner_services.api.routes.events.check_rpc_rate")
    @patch("airunner_services.api.routes.events._safe_send_json")
    async def test_unauthenticated_rejected(
        self,
        mock_send: MagicMock,
        mock_check_rpc: MagicMock,
        mock_dispatch: MagicMock,
    ) -> None:
        """account_id=None → check_rpc_rate(None)==False → 429, no
        dispatch."""
        from airunner_services.api.routes.events import (
            _handle_rpc_message,
        )

        mock_check_rpc.return_value = False

        ws = MagicMock()
        raw = {"type": "rpc", "id": "req-1", "method": "GET",
               "path": "/api/v1/economy/gems/balance", "body": {}}

        await _handle_rpc_message(raw, ws, None)

        mock_check_rpc.assert_called_once_with(None)
        mock_dispatch.assert_not_called()
        mock_send.assert_called_once()
        sent = mock_send.call_args[0][1]
        assert sent["status"] == 429
