"""Unit tests for episodic summarizer wrapper and click-endpoint behavior."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_mock(session_id: int = 1) -> MagicMock:
    """Return a mock ChatSession with the given id."""
    session = MagicMock()
    session.id = session_id
    return session


def _make_chatbot_mock(chatbot_id: int = 42, botname: str = "TestBot"):
    """Return a mock Chatbot dataclass."""
    from collections import namedtuple

    MockChatbot = namedtuple("MockChatbot", ["id", "botname", "deleted"])
    return MockChatbot(id=chatbot_id, botname=botname, deleted=False)


# ---------------------------------------------------------------------------
# Test: summarize_session async wrapper delegates to sync helper
# ---------------------------------------------------------------------------


class TestSummarizeSessionWrapper:
    """Verify summarize_session offloads work via asyncio.to_thread."""

    def test_delegates_to_sync_helper_with_correct_args(self):
        """summarize_session awaits asyncio.to_thread with
        _summarize_session_sync and the right arguments."""
        from airunner_services.llm.episodic_summarizer import (
            summarize_session,
        )

        with patch(
            "airunner_services.llm.episodic_summarizer"
            "._summarize_session_sync"
        ) as mock_sync:
            asyncio.run(summarize_session(42, app=None))
            mock_sync.assert_called_once_with(42, None)

    def test_delegates_with_app_passed_through(self):
        """When app is provided, it is forwarded to the sync helper."""
        from airunner_services.llm.episodic_summarizer import (
            summarize_session,
        )
        mock_app = MagicMock()

        with patch(
            "airunner_services.llm.episodic_summarizer"
            "._summarize_session_sync"
        ) as mock_sync:
            asyncio.run(summarize_session(7, app=mock_app))
            mock_sync.assert_called_once_with(7, mock_app)


# ---------------------------------------------------------------------------
# Test: click/load endpoints do NOT trigger summarization
# ---------------------------------------------------------------------------


class TestClickEndpointsDoNotSummarize:
    """Verify loading a chatbot session does not call summarize_session."""

    def test_rpc_uwu_session_does_not_summarize(self):
        """_rpc_uwu_session never calls summarize_session, even when
        get_or_create_session would have returned a cold_id."""
        from airunner_services.api.routes.rpc_handlers import (
            _rpc_uwu_session,
        )
        from airunner_services.llm.session_manager import SessionManager

        conv = MagicMock()
        conv.id = 10
        session = _make_session_mock(session_id=5)
        chatbot = _make_chatbot_mock(chatbot_id=42)

        with patch.object(
            SessionManager,
            "get_or_create_session",
            return_value=(session, conv, 99, 4.5),
        ), patch(
            "airunner_services.database.models.chatbot.Chatbot"
        ) as MockChatbot:
            MockChatbot.objects.get.return_value = chatbot

            with patch(
                "airunner_services.llm.episodic_summarizer.summarize_session"
            ) as mock_summarize:
                body = {"chatbot_id": 42, "user_id": None}
                result = asyncio.run(_rpc_uwu_session(body))

                assert result["status"] == 200
                assert result["body"]["conversation_id"] == 10
                assert result["body"]["session_id"] == 5
                mock_summarize.assert_not_called()

    def test_get_uwu_session_does_not_summarize(self):
        """get_uwu_session never calls summarize_session, even when
        get_or_create_session would have returned a cold_id."""
        from airunner_services.api.routes.llm_http_routes import (
            get_uwu_session,
        )
        from airunner_services.llm.session_manager import SessionManager

        conv = MagicMock()
        conv.id = 20
        session = _make_session_mock(session_id=8)
        chatbot = _make_chatbot_mock(chatbot_id=42)

        with patch.object(
            SessionManager,
            "get_or_create_session",
            return_value=(session, conv, 77, 5.0),
        ), patch(
            "airunner_services.database.models.chatbot.Chatbot"
        ) as MockChatbot:
            MockChatbot.objects.get.return_value = chatbot

            with patch(
                "airunner_services.llm.episodic_summarizer.summarize_session"
            ) as mock_summarize:
                result = asyncio.run(get_uwu_session(chatbot_id=42))

                assert result["conversation_id"] == 20
                assert result["session_id"] == 8
                mock_summarize.assert_not_called()
