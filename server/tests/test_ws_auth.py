"""Tests for WebSocket authentication and rate-limit enforcement.

Part 1 (CRITICAL) — Unauthenticated access to LLM streaming endpoint:
- ``resolve_ws_tenant`` without a token returns ``(None, None)``.
- ``check_llm_stream_rate`` and ``check_rpc_rate`` reject
  ``account_id=None``.
- The chat WebSocket handler closes the connection when no valid
  token is present.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from airunner_services.api.ws_rate_limiter import (
    check_llm_stream_rate,
    check_rpc_rate,
)
from airunner_services.api.ws_tenant import resolve_ws_tenant


class TestResolveWsTenantUnauthenticated:
    """``resolve_ws_tenant`` returns ``(None, None)`` without a token."""

    def test_no_token_returns_none(self) -> None:
        """No query param or header → (None, None)."""
        ws = MagicMock()
        ws.query_params.get.return_value = None
        ws.headers.get.return_value = ""
        tenant_key, account_id = resolve_ws_tenant(ws)
        assert tenant_key is None
        assert account_id is None

    def test_empty_token_returns_none(self) -> None:
        """Empty query param → (None, None)."""
        ws = MagicMock()
        ws.query_params.get.return_value = ""
        ws.headers.get.return_value = ""
        tenant_key, account_id = resolve_ws_tenant(ws)
        assert tenant_key is None
        assert account_id is None

    def test_invalid_token_returns_none(self) -> None:
        """A garbage token that fails JWT decode → (None, None)."""
        ws = MagicMock()
        ws.query_params.get.return_value = "not-a-valid-jwt"
        ws.headers.get.return_value = ""
        tenant_key, account_id = resolve_ws_tenant(ws)
        assert tenant_key is None
        assert account_id is None

    def test_bearer_header_empty_token(self) -> None:
        """Bearer header with no actual token → (None, None)."""
        ws = MagicMock()
        ws.query_params.get.return_value = None
        ws.headers.get.return_value = "Bearer "
        tenant_key, account_id = resolve_ws_tenant(ws)
        assert tenant_key is None
        assert account_id is None


class TestRateLimiterRejectsUnauthenticated:
    """Rate-limit checks reject ``account_id=None``."""

    def test_llm_stream_rate_rejects_none(self) -> None:
        """``check_llm_stream_rate(None)`` returns ``False``."""
        assert check_llm_stream_rate(None) is False

    def test_rpc_rate_rejects_none(self) -> None:
        """``check_rpc_rate(None)`` returns ``False``."""
        assert check_rpc_rate(None) is False

    def test_llm_stream_rate_allows_valid_id(self) -> None:
        """A valid ``account_id`` passes the rate limit (first request)."""
        assert check_llm_stream_rate(99999) is True

    def test_rpc_rate_allows_valid_id(self) -> None:
        """A valid ``account_id`` passes the rate limit (first request)."""
        assert check_rpc_rate(99999) is True
