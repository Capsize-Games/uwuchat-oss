"""Unit tests for defense-in-depth RPC auth guards (Part 4, round 5).

Tests that conversation and settings RPC handlers reject unauthenticated
callers at the handler level, not only at the upstream dispatcher.
"""

from __future__ import annotations

from unittest.mock import patch



# ── Conversation handlers ──────────────────────────────────────────────


class TestConvAuthGuard:
    """Each conversation handler must reject when _conv_auth returns None."""

    @patch(
        "server.src.airunner_services.api.routes."
        "rpc_conversation_handlers._conv_auth",
        return_value=None,
    )
    async def test_list_rejected(self, mock_auth):
        from server.src.airunner_services.api.routes.rpc_conversation_handlers import (
            _rpc_conversations_list,
        )

        result = await _rpc_conversations_list({}, ws=object())
        assert result["status"] == 401

    @patch(
        "server.src.airunner_services.api.routes."
        "rpc_conversation_handlers._conv_auth",
        return_value=None,
    )
    async def test_create_rejected(self, mock_auth):
        from server.src.airunner_services.api.routes.rpc_conversation_handlers import (
            _rpc_conversations_create,
        )

        result = await _rpc_conversations_create({}, ws=object())
        assert result["status"] == 401

    @patch(
        "server.src.airunner_services.api.routes."
        "rpc_conversation_handlers._conv_auth",
        return_value=None,
    )
    async def test_delete_rejected(self, mock_auth):
        from server.src.airunner_services.api.routes.rpc_conversation_handlers import (
            _rpc_conversations_delete,
        )

        path_params = {"conv_id": "1"}
        result = await _rpc_conversations_delete(
            {}, ws=object(), path_params=path_params,
        )
        assert result["status"] == 401

    @patch(
        "server.src.airunner_services.api.routes."
        "rpc_conversation_handlers._conv_auth",
        return_value=None,
    )
    async def test_session_rejected(self, mock_auth):
        from server.src.airunner_services.api.routes.rpc_conversation_handlers import (
            _rpc_conversations_session,
        )

        result = await _rpc_conversations_session({}, ws=object())
        assert result["status"] == 401

    @patch(
        "server.src.airunner_services.api.routes."
        "rpc_conversation_handlers._conv_auth",
        return_value=None,
    )
    async def test_select_rejected(self, mock_auth):
        from server.src.airunner_services.api.routes.rpc_conversation_handlers import (
            _rpc_conversations_select,
        )

        result = await _rpc_conversations_select({}, ws=object())
        assert result["status"] == 401

    @patch(
        "server.src.airunner_services.api.routes."
        "rpc_conversation_handlers._conv_auth",
        return_value=None,
    )
    async def test_truncate_rejected(self, mock_auth):
        from server.src.airunner_services.api.routes.rpc_conversation_handlers import (
            _rpc_conversations_truncate,
        )

        result = await _rpc_conversations_truncate(
            {"conversation_id": 1, "keep_count": 1}, ws=object(),
        )
        assert result["status"] == 401

    @patch(
        "server.src.airunner_services.api.routes."
        "rpc_conversation_handlers._conv_auth",
        return_value=None,
    )
    async def test_previews_rejected(self, mock_auth):
        from server.src.airunner_services.api.routes.rpc_conversation_handlers import (
            _rpc_conversation_previews,
        )

        result = await _rpc_conversation_previews(
            {"chatbot_ids": [1]}, ws=object(),
        )
        assert result["status"] == 401


# ── Settings handlers ──────────────────────────────────────────────────


class TestSettingsAuthGuard:
    """Each settings handler must reject when _settings_auth returns None."""

    @patch(
        "server.src.airunner_services.api.routes."
        "rpc_settings._settings_auth",
        return_value=None,
    )
    async def test_update_by_id_rejected(self, mock_auth):
        from server.src.airunner_services.api.routes.rpc_settings import (
            _rpc_settings_update_by_id,
        )

        path_params = {"name": "Chatbot", "resource_id": "1"}
        result = await _rpc_settings_update_by_id(
            {"values": {}}, ws=object(), path_params=path_params,
        )
        assert result["status"] == 401

    @patch(
        "server.src.airunner_services.api.routes."
        "rpc_settings._settings_auth",
        return_value=None,
    )
    async def test_delete_rejected(self, mock_auth):
        from server.src.airunner_services.api.routes.rpc_settings import (
            _rpc_settings_delete,
        )

        path_params = {"name": "Chatbot", "resource_id": "1"}
        result = await _rpc_settings_delete(
            {}, ws=object(), path_params=path_params,
        )
        assert result["status"] == 401

    @patch(
        "server.src.airunner_services.api.routes."
        "rpc_settings._settings_auth",
        return_value=None,
    )
    async def test_reset_defaults_rejected(self, mock_auth):
        from server.src.airunner_services.api.routes.rpc_settings import (
            _rpc_settings_reset_defaults,
        )

        path_params = {"name": "Chatbot", "resource_id": "1"}
        result = await _rpc_settings_reset_defaults(
            {}, ws=object(), path_params=path_params,
        )
        assert result["status"] == 401

    @patch(
        "server.src.airunner_services.api.routes."
        "rpc_settings._settings_auth",
        return_value=None,
    )
    async def test_make_current_rejected(self, mock_auth):
        from server.src.airunner_services.api.routes.rpc_settings import (
            _rpc_settings_make_current,
        )

        path_params = {"name": "Chatbot", "resource_id": "1"}
        result = await _rpc_settings_make_current(
            {}, ws=object(), path_params=path_params,
        )
        assert result["status"] == 401

    @patch(
        "server.src.airunner_services.api.routes."
        "rpc_settings._settings_auth",
        return_value=None,
    )
    async def test_query_rejected(self, mock_auth):
        from server.src.airunner_services.api.routes.rpc_settings import (
            _rpc_settings_query,
        )

        path_params = {"name": "Chatbot"}
        result = await _rpc_settings_query(
            {}, ws=object(), path_params=path_params,
        )
        assert result["status"] == 401

    @patch(
        "server.src.airunner_services.api.routes."
        "rpc_settings._settings_auth",
        return_value=None,
    )
    async def test_first_rejected(self, mock_auth):
        from server.src.airunner_services.api.routes.rpc_settings import (
            _rpc_settings_first,
        )

        path_params = {"name": "Chatbot"}
        result = await _rpc_settings_first(
            {}, ws=object(), path_params=path_params,
        )
        assert result["status"] == 401
