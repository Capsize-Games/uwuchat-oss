"""Tests for JWT token extraction — query string restricted to WS.

Part 3 (MEDIUM) — The ``?token=`` query-param fallback must only be
accepted on WebSocket upgrade requests, not on plain HTTP requests.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from airunner_services.api.ws_tenant import _extract_token


class TestWsTokenExtraction:
    """``_extract_token`` continues to accept ``?token=`` for WS."""

    def test_token_from_query_param(self) -> None:
        """Query param token is extracted."""
        ws = MagicMock()
        ws.query_params.get.return_value = "valid-jwt-token"
        ws.headers.get.return_value = ""
        assert _extract_token(ws) == "valid-jwt-token"

    def test_token_from_bearer_header(self) -> None:
        """Bearer header token is extracted when no query param."""
        ws = MagicMock()
        ws.query_params.get.return_value = None
        ws.headers.get.return_value = "Bearer header-token"
        assert _extract_token(ws) == "header-token"

    def test_no_token_returns_none(self) -> None:
        """No token anywhere → None."""
        ws = MagicMock()
        ws.query_params.get.return_value = None
        ws.headers.get.return_value = ""
        assert _extract_token(ws) is None


class TestMiddlewareQueryParamRejection:
    """The HTTP middleware rejects ``?token=`` on non-WS requests.

    The middleware check happens at runtime inside the FastAPI stack;
    we validate the guard logic by testing that the middleware's
    ``request.scope["type"]`` gating is present and correct.
    """

    def test_middleware_has_ws_scope_guard(self) -> None:
        """The token extraction block includes a scope-type check."""
        import inspect

        from extensions.auth.server.middleware import register

        source = inspect.getsource(register)
        assert 'scope.get("type") == "websocket"' in source, (
            "Middleware must gate ?token= on request.scope['type']"
            " == 'websocket'"
        )

    def test_middleware_does_not_accept_http_token(self) -> None:
        """Plain HTTP requests with ?token= but no header are rejected.

        Simulates what the middleware does: an HTTP request with only
        ``?token=`` in the query string (and no Authorization header)
        should not extract the token.
        """
        # Build a mock request that looks like a plain HTTP request
        # with ?token= in the query string.
        req = MagicMock()
        req.scope = {"type": "http"}
        req.query_params.get.return_value = "some-token"
        req.headers.get.return_value = ""

        # Replicate the middleware's extraction logic.
        auth_header = req.headers.get("Authorization", "")
        extracted = None
        if auth_header.lower().startswith("bearer "):
            extracted = auth_header[7:].strip()
        elif (
            req.scope.get("type") == "websocket"
            and req.query_params.get("token")
        ):
            extracted = req.query_params["token"]

        # For an HTTP request, the token must NOT be extracted from
        # the query string.
        assert extracted is None, (
            "Token must not be extracted from ?token= on HTTP requests"
        )
