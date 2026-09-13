"""Unit tests for WebSocket tenant scoping (ws_tenant.py).

Verifies that WS tenant resolution correctly decodes JWT tokens and
sets tenant context — the mechanism that prevents WS connections from
silently falling back to ``tenant_anonymous``.
"""

from __future__ import annotations

from unittest.mock import MagicMock


from airunner_services.api.ws_tenant import (
    _extract_token,
    resolve_ws_tenant,
)


def _mock_websocket(query_params: dict | None = None) -> MagicMock:
    """Build a mock WebSocket with query_params and headers."""
    ws = MagicMock()
    ws.query_params = query_params or {}
    ws.headers = {}
    return ws


# ---------------------------------------------------------------------------
# Token extraction
# ---------------------------------------------------------------------------


def test_extract_token_from_query_string():
    """Token is extracted from ?token= query parameter."""
    ws = _mock_websocket({"token": "test-jwt-token"})
    assert _extract_token(ws) == "test-jwt-token"


def test_extract_token_from_authorization_header():
    """Token is extracted from Authorization: Bearer header."""
    ws = _mock_websocket()
    ws.headers = {"authorization": "Bearer header-token"}
    assert _extract_token(ws) == "header-token"


def test_extract_token_query_param_preferred():
    """Query parameter takes precedence over header."""
    ws = _mock_websocket({"token": "query-token"})
    ws.headers = {"authorization": "Bearer header-token"}
    assert _extract_token(ws) == "query-token"


def test_extract_token_none_when_missing():
    """Returns None when no token source is present."""
    ws = _mock_websocket()
    assert _extract_token(ws) is None


# ---------------------------------------------------------------------------
# resolve_ws_tenant
# ---------------------------------------------------------------------------


def test_resolve_ws_tenant_no_token():
    """Returns (None, None) for an unauthenticated socket."""
    ws = _mock_websocket()
    tenant_key, account_id = resolve_ws_tenant(ws)
    assert tenant_key is None
    assert account_id is None


def test_resolve_ws_tenant_invalid_token():
    """Returns (None, None) for a garbage token string."""
    ws = _mock_websocket({"token": "not-a-valid-jwt"})
    tenant_key, account_id = resolve_ws_tenant(ws)
    assert tenant_key is None
    assert account_id is None


def test_resolve_ws_tenant_valid_access_token():
    """Returns tenant key and account ID for a valid access token."""
    from unittest.mock import patch
    from extensions.auth.server.jwt import create_access_token

    token = create_access_token(42, "tenant_abc123")
    ws = _mock_websocket({"token": token})
    # Mock _check_account_status to return active-account tuple.
    # The real DB has no account 42 in unit tests, so the actual
    # function would return ("deleted", 0) and reject the connection.
    with patch(
        "extensions.auth.server.middleware._check_account_status",
        return_value=(None, 0),
    ):
        tenant_key, account_id = resolve_ws_tenant(ws)
    assert tenant_key is not None
    assert account_id == 42


def test_resolve_ws_tenant_refresh_token_rejected():
    """A refresh token (type != 'access') is not accepted for WS auth."""
    from extensions.auth.server.jwt import create_refresh_token

    token = create_refresh_token(7)
    ws = _mock_websocket({"token": token})
    tenant_key, account_id = resolve_ws_tenant(ws)
    assert tenant_key is None
    assert account_id is None
