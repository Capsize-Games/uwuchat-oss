"""Tests for RecentConversationContextBuilder cross-chatbot isolation.

Verifies that recent-conversation context is scoped to a single chatbot
and never leaks content across chatbot boundaries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from airunner_services.conversations.recent_context_builder import (
    RecentConversationContextBuilder,
)


class TestRecentConversationContextBuilder:
    """Unit tests for recent-conversation context builder scoping."""

    @staticmethod
    def _make_conv(
        conv_id: int,
        chatbot_id: int,
        messages: list,
        created_at: datetime | None = None,
    ) -> MagicMock:
        """Build a lightweight mock conversation object."""
        conv = MagicMock()
        conv.id = conv_id
        conv.chatbot_id = chatbot_id
        conv.value = messages
        conv.summary = None
        conv.last_analyzed_message_id = 0
        conv.created_at = created_at or datetime.now(UTC)
        return conv

    @staticmethod
    def _exchange(user_text: str, bot_text: str) -> list[dict]:
        """Return a minimal user/assistant message pair."""
        return [
            {
                "role": "user",
                "is_bot": False,
                "name": "User",
                "content": user_text,
            },
            {
                "role": "assistant",
                "is_bot": True,
                "name": "Bot",
                "content": bot_text,
            },
        ]

    # ------------------------------------------------------------------
    # Safety: None chatbot_id
    # ------------------------------------------------------------------

    def test_returns_empty_when_chatbot_id_is_none(self) -> None:
        """build_context returns '' when chatbot_id is None (safety gate)."""
        builder = RecentConversationContextBuilder()
        result = builder.build_context(
            current_conversation_id=1, chatbot_id=None,
        )
        assert result == ""

    # ------------------------------------------------------------------
    # Parameter forwarding
    # ------------------------------------------------------------------

    def test_passes_chatbot_id_to_fetch_recent(self) -> None:
        """build_context correctly forwards chatbot_id to _fetch_recent."""
        builder = RecentConversationContextBuilder()
        with patch.object(
            builder, "_fetch_recent", return_value=[]
        ) as mock_fetch:
            builder.build_context(
                current_conversation_id=7, chatbot_id=42,
            )
        mock_fetch.assert_called_once_with(42, 7)

    def test_passes_exclude_id_to_fetch_recent(self) -> None:
        """build_context forwards exclude_id (current conv) to _fetch_recent."""
        builder = RecentConversationContextBuilder()
        with patch.object(
            builder, "_fetch_recent", return_value=[]
        ) as mock_fetch:
            builder.build_context(
                current_conversation_id=99, chatbot_id=10,
            )
        mock_fetch.assert_called_once_with(10, 99)

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_empty_fetch_returns_empty_string(self) -> None:
        """Empty _fetch_recent result → empty string."""
        builder = RecentConversationContextBuilder()
        with patch.object(
            builder, "_fetch_recent", return_value=[]
        ):
            result = builder.build_context(
                current_conversation_id=1, chatbot_id=10,
            )
        assert result == ""

    def test_all_empty_blocks_returns_empty_string(self) -> None:
        """Conversations with no usable messages produce empty string."""
        builder = RecentConversationContextBuilder()
        empty_conv = self._make_conv(1, 10, [])
        with patch.object(
            builder, "_fetch_recent", return_value=[empty_conv]
        ):
            result = builder.build_context(
                current_conversation_id=1, chatbot_id=10,
            )
        assert result == ""


class TestFetchRecentChatbotScoping:
    """Integration test: _fetch_recent SQL-level chatbot_id scoping.

    Creates real Chatbot + Conversation rows for two different chatbots
    and verifies that _fetch_recent(chatbot_id=A) never returns rows
    from chatbot B.  This is the regression test for the cross-chatbot
    leak.
    """

    def test_fetch_recent_scopes_to_single_chatbot(self) -> None:
        """Create rows for two chatbots; _fetch_recent(A) excludes B."""
        import uuid
        from airunner_services.database.models.chatbot import Chatbot
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        tag = uuid.uuid4().hex[:8]

        # Create two Chatbot rows (FK constraint requires them).
        with Chatbot.objects.transaction() as tx:
            bot_a = Chatbot(name=f"test_scope_bot_a_{tag}")
            bot_b = Chatbot(name=f"test_scope_bot_b_{tag}")
            tx.add(bot_a)
            tx.add(bot_b)
            tx.flush()
            ca = bot_a.id
            cb = bot_b.id

        assert ca is not None and cb is not None, (
            "Failed to persist test chatbots"
        )

        # Insert two test conversations under distinct chatbot_ids.
        with Conversation.objects.transaction() as tx:
            conv_a = Conversation(
                chatbot_id=ca,
                user_name="test_scope_user",
                chatbot_name="test_bot_a",
                value=[
                    {
                        "role": "user",
                        "is_bot": False,
                        "name": "User",
                        "content": "hello from bot a",
                    },
                ],
            )
            conv_b = Conversation(
                chatbot_id=cb,
                user_name="test_scope_user",
                chatbot_name="test_bot_b",
                value=[
                    {
                        "role": "user",
                        "is_bot": False,
                        "name": "User",
                        "content": "hello from bot b",
                    },
                ],
            )
            tx.add(conv_a)
            tx.add(conv_b)
            tx.flush()
            id_a = conv_a.id
            id_b = conv_b.id

        assert id_a is not None and id_b is not None, (
            "Failed to persist test conversations"
        )

        try:
            results = RecentConversationContextBuilder._fetch_recent(
                chatbot_id=ca, exclude_id=None,
            )

            # Every returned row must belong to chatbot A.
            result_chatbot_ids = {r.chatbot_id for r in results}
            assert result_chatbot_ids == {ca}, (
                f"_fetch_recent({ca}) returned chatbot_ids "
                f"{result_chatbot_ids}; expected {{ {ca} }}"
            )

            # The row from chatbot B must be absent.
            result_ids = {r.id for r in results}
            assert id_b not in result_ids, (
                f"chatbot {cb} row id={id_b} leaked into "
                f"_fetch_recent({ca}) results: {result_ids}"
            )

            # The row from chatbot A must be present.
            assert id_a in result_ids, (
                f"chatbot {ca} row id={id_a} missing from "
                f"_fetch_recent({ca}) results: {result_ids}"
            )
        finally:
            # Clean up regardless of assertion outcome.
            Conversation.objects.query().filter(
                Conversation.chatbot_id.in_([ca, cb]),
            ).delete(synchronize_session=False)
            Chatbot.objects.query().filter(
                Chatbot.id.in_([ca, cb]),
            ).delete(synchronize_session=False)

    def test_fetch_recent_excludes_nonexistent_chatbot(self) -> None:
        """_fetch_recent for an unused chatbot_id returns empty list."""
        results = RecentConversationContextBuilder._fetch_recent(
            chatbot_id=9999009, exclude_id=None,
        )
        assert results == []


class TestFetchRecentQueryConstruction:
    """Verify _fetch_recent constructs the query with chatbot_id filter."""

    def test_query_includes_chatbot_id_filter(self) -> None:
        """The first filter() call is a chatbot_id equality predicate."""
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value.all.return_value = []

        with patch.object(
            Conversation.objects, "query", return_value=mock_query
        ):
            RecentConversationContextBuilder._fetch_recent(
                chatbot_id=42, exclude_id=None,
            )

        # The first filter() call must be chatbot_id == 42.
        call_args_list = mock_query.filter.call_args_list
        assert len(call_args_list) >= 1, (
            "Expected at least one filter() call"
        )

        first_filter_arg = call_args_list[0][0][0]
        # In SQLAlchemy, Conversation.chatbot_id == 42 produces a
        # BinaryExpression whose .right.value is the literal 42.
        right_val = getattr(first_filter_arg, "right", None)
        right_value = getattr(right_val, "value", None)
        assert right_value == 42, (
            f"First filter() arg right.value={right_value}, expected 42"
        )

        # Also verify the left side references chatbot_id.
        left = getattr(first_filter_arg, "left", None)
        left_key = getattr(left, "key", None)
        assert left_key == "chatbot_id", (
            f"First filter() arg left.key={left_key}, "
            f"expected 'chatbot_id'"
        )
