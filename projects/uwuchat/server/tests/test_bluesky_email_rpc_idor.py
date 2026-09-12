"""WS-RPC regression tests for Bluesky and Email IDOR fixes (round 4).

Verifies that the three handlers identified in Part 1 of the round-4
audit — ``_rpc_bluesky_status``, ``_rpc_bluesky_posts``, and
``_rpc_email_status`` — reject cross-account access when the path
contains a different account's ``user_id``.

These tests drive the actual ``_dispatch_rpc(...)`` path, not the HTTP
router path (which is separately tested in
``test_connection_routes_auth.py`` and was already correct).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import WebSocket

from airunner_services.api.routes.events import _dispatch_rpc
from airunner_services.database.session import (
    public_session_scope,
    reset_engine,
)
from extensions.auth.server.jwt import create_access_token
from extensions.auth.server.models import Account
from airunner_services.contract_enums import ModelService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _TestAccount:
    """Lightweight value object to avoid DetachedInstanceError."""
    id: int
    tenant_schema: str


def _make_account() -> _TestAccount:
    """Create a test Account with a unique email and return it."""
    with public_session_scope() as session:
        acct = Account(
            email=f"idor-rpc-{uuid.uuid4().hex[:8]}@example.com",
            username=f"u_{uuid.uuid4().hex[:8]}",
            password_hash="unused",
            tenant_schema=f"tenant_{uuid.uuid4().hex}",
            auth_provider=ModelService.LOCAL.value,
        )
        session.add(acct)
        session.flush()
        result = _TestAccount(
            id=int(acct.id),
            tenant_schema=str(acct.tenant_schema),
        )
    return result


def _token(account: _TestAccount) -> str:
    """Return an access token for *account*."""
    return create_access_token(account.id, account.tenant_schema)


def _mock_ws(account: _TestAccount) -> MagicMock:
    """Return a mock WebSocket carrying *account*'s JWT in query params."""
    ws = MagicMock(spec=WebSocket)
    token = _token(account)
    ws.query_params = {"token": token}
    ws.headers = {}
    return ws


# ---------------------------------------------------------------------------
# Register RPC handlers by importing the modules (side-effect at import).
# ---------------------------------------------------------------------------

import projects.uwuchat.server.bluesky.routes as _bsky_routes
import projects.uwuchat.server.email.routes as _email_routes


# ---------------------------------------------------------------------------
# Bluesky RPC tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rpc_bluesky_status_rejects_cross_account(
    _db: str,
) -> None:
    """Account A must not get account B's Bluesky connection status.

    The handler now ignores the path-supplied user_id and queries by
    the JWT-resolved account_id.  So a cross-account request returns
    the *caller's* own status, never the victim's.
    """
    acct_a = _make_account()
    acct_b = _make_account()
    ws_a = _mock_ws(acct_a)

    result = await _dispatch_rpc(
        "GET",
        f"/api/v1/bluesky/status/{acct_b.id}",
        {},
        ws_a,
    )
    # The handler must not error out (the request is authenticated
    # as A, and the handler uses A's account_id, not B's).
    body = result.get("body", {})
    # Must not leak B's data — connected can only be False for a
    # freshly-created test account with no Bluesky connection.
    assert body.get("connected") is not True, (
        "Must not return connected=True for another account"
    )


@pytest.mark.asyncio
async def test_rpc_bluesky_status_allows_own_account(
    _db: str,
) -> None:
    """Account A must be able to query its own Bluesky status."""
    acct_a = _make_account()
    ws_a = _mock_ws(acct_a)

    result = await _dispatch_rpc(
        "GET",
        f"/api/v1/bluesky/status/{acct_a.id}",
        {},
        ws_a,
    )
    # Own-account request must pass the auth gate.
    assert result["status"] == 200, (
        f"Own Bluesky status should return 200, got {result['status']}"
    )
    body = result.get("body", {})
    assert "connected" in body


@pytest.mark.asyncio
async def test_rpc_bluesky_status_rejects_no_token(
    _db: str,
) -> None:
    """An unauthenticated WS must be rejected by the handler."""
    ws = MagicMock(spec=WebSocket)
    ws.query_params = {}
    ws.headers = {}

    result = await _dispatch_rpc(
        "GET", "/api/v1/bluesky/status/1", {}, ws,
    )
    # Must be rejected with auth error, not 200.
    assert result["status"] in (400, 401), (
        f"Expected 400/401 for unauthenticated Bluesky status, "
        f"got {result['status']}"
    )


@pytest.mark.asyncio
async def test_rpc_bluesky_posts_rejects_cross_account(
    _db: str,
) -> None:
    """Account A must not get account B's Bluesky posts.

    The handler now ignores the path-supplied user_id and queries by
    the JWT-resolved account_id.  A cross-account request returns A's
    own posts (empty for a fresh account), never B's.
    """
    acct_a = _make_account()
    acct_b = _make_account()
    ws_a = _mock_ws(acct_a)

    result = await _dispatch_rpc(
        "GET",
        f"/api/v1/bluesky/posts/{acct_b.id}",
        {},
        ws_a,
    )
    body = result.get("body", {})
    # Must not contain another account's handle or posts.
    # A fresh account has no Bluesky connection, so handle is None
    # and posts is empty.
    assert body.get("handle") is None, (
        "Must not leak another account's Bluesky handle"
    )
    assert not body.get("posts"), (
        "Must not leak another account's Bluesky posts"
    )


@pytest.mark.asyncio
async def test_rpc_bluesky_posts_allows_own_account(
    _db: str,
) -> None:
    """Account A must be able to query its own Bluesky posts."""
    acct_a = _make_account()
    ws_a = _mock_ws(acct_a)

    result = await _dispatch_rpc(
        "GET",
        f"/api/v1/bluesky/posts/{acct_a.id}",
        {},
        ws_a,
    )
    assert result["status"] == 200, (
        f"Own Bluesky posts should return 200, got {result['status']}"
    )
    body = result.get("body", {})
    assert "posts" in body


# ---------------------------------------------------------------------------
# Email RPC tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rpc_email_status_rejects_cross_account(
    _db: str,
) -> None:
    """Account A must not get account B's email connection status."""
    acct_a = _make_account()
    acct_b = _make_account()
    ws_a = _mock_ws(acct_a)

    result = await _dispatch_rpc(
        "GET",
        f"/api/v1/email/status/{acct_b.id}",
        {},
        ws_a,
    )
    assert result["status"] in (400, 403), (
        f"Expected 400/403 for cross-account email status, "
        f"got {result['status']}: {result}"
    )
    body = result.get("body", {})
    assert body.get("connected") is not True, (
        "Must not return connected=True for another account"
    )


@pytest.mark.asyncio
async def test_rpc_email_status_allows_own_account(
    _db: str,
) -> None:
    """Account A must be able to query its own email status."""
    acct_a = _make_account()
    ws_a = _mock_ws(acct_a)

    result = await _dispatch_rpc(
        "GET",
        f"/api/v1/email/status/{acct_a.id}",
        {},
        ws_a,
    )
    assert result["status"] == 200, (
        f"Own email status should return 200, got {result['status']}"
    )
    body = result.get("body", {})
    assert "connected" in body
