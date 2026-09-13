"""Unit tests for chatbot image generation rate limiting (Part 3, round 5).

Tests that the per-chatbot image-generation rate limiter:
  - Allows up to _IMAGE_GEN_MAX_PER_HOUR calls in the window
  - Rejects the (N+1)th call within the window with 429
  - Resolves account_id + chatbot_id for the rate-limit key
"""

from __future__ import annotations

from unittest.mock import patch


from server.src.airunner_services.api.routes.rpc_chatbot_profile import (
    _IMAGE_GEN_MAX_PER_HOUR,
    _check_image_gen_rate_limit,
    _image_gen_rate_key,
    _IMAGE_GEN_RATE_WINDOW,
)


class TestImageGenRateLimiter:
    """In-memory sliding-window rate limiter for image generation."""

    def setup_method(self):
        _IMAGE_GEN_RATE_WINDOW.clear()

    def test_rate_key_format(self):
        """Key is account_id:chatbot_id."""
        key = _image_gen_rate_key(1, 42)
        assert key == "1:42"

    def test_allows_up_to_limit(self):
        """First N calls within the window are allowed."""
        for _ in range(_IMAGE_GEN_MAX_PER_HOUR):
            assert _check_image_gen_rate_limit(1, 42) is True

    def test_rejects_after_limit(self):
        """The (N+1)th call is rejected."""
        for _ in range(_IMAGE_GEN_MAX_PER_HOUR):
            assert _check_image_gen_rate_limit(1, 42) is True
        assert _check_image_gen_rate_limit(1, 42) is False

    def test_different_chatbots_independent(self):
        """Rate limit is per-chatbot, not just per-account."""
        # Exhaust chatbot 42.
        for _ in range(_IMAGE_GEN_MAX_PER_HOUR):
            assert _check_image_gen_rate_limit(1, 42) is True
        assert _check_image_gen_rate_limit(1, 42) is False
        # Chatbot 99 (same account) is unaffected.
        assert _check_image_gen_rate_limit(1, 99) is True


class TestImageGenRPCAuth:
    """The RPC handler rejects unauthenticated callers."""

    @patch(
        "airunner_services.api.ws_tenant.resolve_ws_tenant"
    )
    async def test_unauthenticated_rejected(self, mock_resolve):
        """Handler returns 401 when account_id is None."""
        from server.src.airunner_services.api.routes.rpc_chatbot_profile import (
            _rpc_generate_chatbot_images,
        )

        mock_resolve.return_value = ("tenant_x", None)
        kw = {
            "ws": object(),
            "path_params": {"chatbot_id": "42"},
        }
        result = await _rpc_generate_chatbot_images({}, **kw)
        assert result["status"] == 401
        assert "Authentication required" in result["body"]["error"]

    async def test_no_ws_rejected(self):
        """Handler returns 401 when no ws is provided."""
        from server.src.airunner_services.api.routes.rpc_chatbot_profile import (
            _rpc_generate_chatbot_images,
        )

        kw = {"path_params": {"chatbot_id": "42"}}
        result = await _rpc_generate_chatbot_images({}, **kw)
        assert result["status"] == 401

    @patch(
        "airunner_services.api.ws_tenant.resolve_ws_tenant"
    )
    @patch(
        "server.src.airunner_services.api.routes.rpc_chatbot_profile."
        "_check_image_gen_rate_limit",
        return_value=False,
    )
    async def test_rate_limited_rejected(
        self, mock_rate, mock_resolve
    ):
        """Handler returns 429 when rate limit is exceeded."""
        from server.src.airunner_services.api.routes.rpc_chatbot_profile import (
            _rpc_generate_chatbot_images,
        )

        mock_resolve.return_value = ("tenant_x", 1)
        kw = {
            "ws": object(),
            "path_params": {"chatbot_id": "42"},
        }
        result = await _rpc_generate_chatbot_images({}, **kw)
        assert result["status"] == 429
