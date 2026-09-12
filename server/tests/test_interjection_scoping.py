"""Tests for WsEventBus account-scoped event isolation.

Part 1 — proactive_message must only reach the owning account's
subscribers, and unauthenticated subscriptions to account-scoped
event types must be rejected.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from airunner_services.api.routes.events import _handle_subscribe
from airunner_services.api.routes.events_bus import _WsSubscriber, WsEventBus
from airunner_services.api.routes.events_rpc import (
    _ACCOUNT_SCOPED_EVENTS,
    EVENT_GEMS_BALANCE,
    EVENT_PROACTIVE_MESSAGE,
    EVENT_ROOM_MESSAGE,
    EVENT_WEATHER_DATA,
)


class TestAccountScopedEvents:
    """All expected event types are in the account-scoped set."""

    def test_proactive_message_is_account_scoped(self) -> None:
        assert EVENT_PROACTIVE_MESSAGE in _ACCOUNT_SCOPED_EVENTS

    def test_gems_balance_is_account_scoped(self) -> None:
        assert EVENT_GEMS_BALANCE in _ACCOUNT_SCOPED_EVENTS

    def test_room_message_is_account_scoped(self) -> None:
        assert EVENT_ROOM_MESSAGE in _ACCOUNT_SCOPED_EVENTS

    def test_weather_data_is_account_scoped(self) -> None:
        assert EVENT_WEATHER_DATA in _ACCOUNT_SCOPED_EVENTS


class TestUnauthenticatedSubscribeRejected:
    """An unauthenticated subscriber (account_id=None) cannot subscribe
    to account-scoped event types."""

    @pytest.mark.asyncio
    async def test_proactive_message_rejected_for_anon(self) -> None:
        sub = _WsSubscriber(AsyncMock(), account_id=None)
        ws = AsyncMock()
        await _handle_subscribe(
            {"events": ["proactive_message"]}, ws, sub, WsEventBus(),
        )
        ws.send_json.assert_called_once()
        call_arg = ws.send_json.call_args[0][0]
        assert call_arg["type"] == "error"
        assert "Authentication required" in call_arg["error"]

    @pytest.mark.asyncio
    async def test_room_message_rejected_for_anon(self) -> None:
        sub = _WsSubscriber(AsyncMock(), account_id=None)
        ws = AsyncMock()
        await _handle_subscribe(
            {"events": ["room_message"]}, ws, sub, WsEventBus(),
        )
        ws.send_json.assert_called_once()
        call_arg = ws.send_json.call_args[0][0]
        assert call_arg["type"] == "error"

    @pytest.mark.asyncio
    async def test_gems_balance_rejected_for_anon(self) -> None:
        sub = _WsSubscriber(AsyncMock(), account_id=None)
        ws = AsyncMock()
        await _handle_subscribe(
            {"events": ["gems_balance"]}, ws, sub, WsEventBus(),
        )
        ws.send_json.assert_called_once()
        call_arg = ws.send_json.call_args[0][0]
        assert call_arg["type"] == "error"

    @pytest.mark.asyncio
    async def test_weather_data_rejected_for_anon(self) -> None:
        sub = _WsSubscriber(AsyncMock(), account_id=None)
        ws = AsyncMock()
        await _handle_subscribe(
            {"events": ["weather_data"]}, ws, sub, WsEventBus(),
        )
        ws.send_json.assert_called_once()
        call_arg = ws.send_json.call_args[0][0]
        assert call_arg["type"] == "error"

    @pytest.mark.asyncio
    async def test_public_event_allowed_for_anon(self) -> None:
        """Public events like 'images' are still allowed without auth."""
        sub = _WsSubscriber(AsyncMock(), account_id=None)
        ws = AsyncMock()
        await _handle_subscribe(
            {"events": ["images"]}, ws, sub, WsEventBus(),
        )
        ws.send_json.assert_called_once()
        call_arg = ws.send_json.call_args[0][0]
        assert call_arg["type"] == "subscribed"


class TestBroadcastAccountScoping:
    """broadcast() with account_id only delivers to matching subscribers."""

    def test_same_account_receives(self) -> None:
        bus = WsEventBus()
        sub = _WsSubscriber(AsyncMock(), account_id=7)
        bus.subscribe(sub, ["proactive_message"])

        bus.broadcast(
            "proactive_message",
            {"content": "hello"},
            account_id=7,
        )
        assert sub._sync_queue.qsize() == 1

    def test_different_account_excluded(self) -> None:
        bus = WsEventBus()
        sub_a = _WsSubscriber(AsyncMock(), account_id=7)
        sub_b = _WsSubscriber(AsyncMock(), account_id=99)
        bus.subscribe(sub_a, ["proactive_message"])
        bus.subscribe(sub_b, ["proactive_message"])

        bus.broadcast(
            "proactive_message",
            {"content": "for account 7 only"},
            account_id=7,
        )
        assert sub_a._sync_queue.qsize() == 1
        assert sub_b._sync_queue.qsize() == 0

    def test_broadcast_without_account_id_goes_to_all(self) -> None:
        bus = WsEventBus()
        sub_a = _WsSubscriber(AsyncMock(), account_id=7)
        sub_b = _WsSubscriber(AsyncMock(), account_id=99)
        bus.subscribe(sub_a, ["images"])
        bus.subscribe(sub_b, ["images"])

        bus.broadcast("images", {"type": "reload"})
        assert sub_a._sync_queue.qsize() == 1
        assert sub_b._sync_queue.qsize() == 1
