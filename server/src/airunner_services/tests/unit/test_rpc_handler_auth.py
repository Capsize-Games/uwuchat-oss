"""Defense-in-depth tests for RPC handler auth checks (round 4, Part 4).

Verifies that handlers in rpc_canvas, rpc_privacy, rpc_rooms, and
rpc_character_handlers reject unauthenticated calls with a 400/401
response rather than succeeding.

These drive through the actual ``_dispatch_rpc(...)`` path.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import WebSocket

from airunner_services.api.routes.events import _dispatch_rpc

# Register RPC handlers by importing the modules (side-effect at import).


def _unauth_ws():
    """Return a mock WebSocket with no auth token."""
    ws = MagicMock(spec=WebSocket)
    ws.query_params = {}
    ws.headers = {}
    return ws


# ── rpc_canvas ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_canvas_doc_get_rejects_unauthenticated():
    ws = _unauth_ws()
    result = await _dispatch_rpc("GET", "/api/v1/canvas/document", {}, ws)
    assert result["status"] in (400, 401), (
        f"Expected 400/401, got {result['status']}"
    )


@pytest.mark.asyncio
async def test_canvas_doc_save_rejects_unauthenticated():
    ws = _unauth_ws()
    result = await _dispatch_rpc(
        "PUT", "/api/v1/canvas/document", {"document": "{}"}, ws,
    )
    assert result["status"] in (400, 401), (
        f"Expected 400/401, got {result['status']}"
    )


@pytest.mark.asyncio
async def test_canvas_layers_rejects_unauthenticated():
    ws = _unauth_ws()
    result = await _dispatch_rpc("GET", "/api/v1/canvas/layers", {}, ws)
    assert result["status"] in (400, 401), (
        f"Expected 400/401, got {result['status']}"
    )


# ── rpc_privacy ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_privacy_get_rejects_unauthenticated():
    ws = _unauth_ws()
    result = await _dispatch_rpc("GET", "/api/v1/settings/privacy", {}, ws)
    assert result["status"] in (400, 401), (
        f"Expected 400/401, got {result['status']}"
    )


@pytest.mark.asyncio
async def test_privacy_update_rejects_unauthenticated():
    ws = _unauth_ws()
    result = await _dispatch_rpc(
        "PUT", "/api/v1/settings/privacy", {"services": {}}, ws,
    )
    assert result["status"] in (400, 401), (
        f"Expected 400/401, got {result['status']}"
    )


# ── rpc_rooms ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rooms_list_rejects_unauthenticated():
    ws = _unauth_ws()
    result = await _dispatch_rpc("GET", "/api/v1/rooms", {}, ws)
    assert result["status"] in (400, 401), (
        f"Expected 400/401, got {result['status']}"
    )


@pytest.mark.asyncio
async def test_room_messages_rejects_unauthenticated():
    ws = _unauth_ws()
    result = await _dispatch_rpc(
        "GET", "/api/v1/rooms/1/messages", {"limit": 10}, ws,
    )
    assert result["status"] in (400, 401), (
        f"Expected 400/401, got {result['status']}"
    )


@pytest.mark.asyncio
async def test_room_observe_rejects_unauthenticated():
    ws = _unauth_ws()
    result = await _dispatch_rpc("POST", "/api/v1/rooms/1/observe", {}, ws)
    assert result["status"] in (400, 401), (
        f"Expected 400/401, got {result['status']}"
    )


# ── rpc_character_handlers ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_presets_rejects_unauthenticated():
    ws = _unauth_ws()
    result = await _dispatch_rpc(
        "GET", "/api/v1/llm/settings-presets", {}, ws,
    )
    assert result["status"] in (400, 401), (
        f"Expected 400/401, got {result['status']}"
    )


@pytest.mark.asyncio
async def test_randomize_character_rejects_unauthenticated():
    ws = _unauth_ws()
    result = await _dispatch_rpc(
        "POST", "/api/v1/llm/randomize-character", {}, ws,
    )
    assert result["status"] in (400, 401), (
        f"Expected 400/401, got {result['status']}"
    )
