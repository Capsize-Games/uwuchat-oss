"""Tests for non-dict entry guards in DatabaseChatMessageHistory.

Validates that every loop iterating ``_conversation.value`` is
protected against stray non-dict entries (e.g. plain strings) that
would otherwise crash ``.get()`` calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestConversationValueGuards:
    """Verify isinstance(existing, dict) guards on value iteration."""

    @staticmethod
    def _make_message(cls_name: str, role: str, content: str) -> MagicMock:
        """Build a minimal mock LangChain message."""
        msg = MagicMock()
        msg.__class__.__name__ = cls_name
        msg.content = content
        msg.additional_kwargs = {}
        if cls_name == "AIMessage":
            msg.tool_calls = None
        return msg

    def test_add_message_survives_stray_string_in_value(self) -> None:
        """add_message persists even when value contains a stray string."""
        from airunner_services.llm.managers.database_chat_message_history import (
            DatabaseChatMessageHistory,
        )

        history = DatabaseChatMessageHistory.__new__(
            DatabaseChatMessageHistory
        )
        history.ephemeral = False
        history.call_chain_id = None
        history.conversation_id = 42
        history.logger = MagicMock()

        # Fake a conversation whose .value already has a stray string
        # among normal dict entries.
        conv = MagicMock()
        conv.id = 42
        conv.value = [
            {"role": "user", "content": "hi", "timestamp": ""},
            "stray bare string",
            {"role": "assistant", "content": "hello", "timestamp": ""},
        ]
        history._conversation = conv

        # Patch _load_conversation to be a no-op (already loaded).
        history._load_conversation = MagicMock()

        fake_update = MagicMock(return_value=True)
        conv_objects = MagicMock()
        conv_objects.update = fake_update

        user_msg = self._make_message("HumanMessage", "user", "new turn")

        with patch(
            "airunner_services.llm.managers.database_chat_message_history"
            "._message_build.Conversation",
            MagicMock(objects=conv_objects),
        ):
            history.add_message(user_msg)

        # The stray string must NOT have caused the method to silently
        # fail — the new message must be appended.
        assert len(conv.value) == 4, (
            "Expected 4 entries (3 original + 1 new) "
            "but got %d" % len(conv.value)
        )
        last = conv.value[-1]
        assert isinstance(last, dict), (
            "Last entry must be a dict, got %s" % type(last).__name__
        )
        assert last.get("role") == "user"
        assert last.get("content") == "new turn"

        # Logger must not have reported an error.
        history.logger.error.assert_not_called()

    def test_messages_property_skips_non_dict_entries(self) -> None:
        """messages property skips stray strings without crashing."""
        from airunner_services.llm.managers.database_chat_message_history import (
            DatabaseChatMessageHistory,
        )

        history = DatabaseChatMessageHistory.__new__(
            DatabaseChatMessageHistory
        )
        history.ephemeral = False
        history.conversation_id = 1
        history.logger = MagicMock()

        conv = MagicMock()
        conv.id = 1
        conv.value = [
            {"role": "user", "content": "a", "timestamp": ""},
            "bad string",
            {"role": "assistant", "content": "b", "timestamp": ""},
        ]
        history._conversation = conv

        fake_get = MagicMock(return_value=conv)
        conv_objects = MagicMock()
        conv_objects.get = fake_get

        with patch(
            "airunner_services.llm.managers.database_chat_message_history"
            "._base.Conversation",
            MagicMock(objects=conv_objects),
        ):
            msgs = history.messages

        assert len(msgs) == 2, (
            "Expected 2 messages, got %d" % len(msgs)
        )

    def test_get_tool_call_metadata_skips_non_dict_entries(self) -> None:
        """get_tool_call_metadata skips stray strings without crashing."""
        from airunner_services.llm.managers.database_chat_message_history import (
            DatabaseChatMessageHistory,
        )

        history = DatabaseChatMessageHistory.__new__(
            DatabaseChatMessageHistory
        )
        history.ephemeral = False
        history.conversation_id = 1
        history.logger = MagicMock()

        conv = MagicMock()
        conv.id = 1
        conv.value = [
            {"metadata_type": "tool_calls", "name": "search"},
            "stray string",
        ]
        history._conversation = conv

        fake_get = MagicMock(return_value=conv)
        conv_objects = MagicMock()
        conv_objects.get = fake_get

        with patch(
            "airunner_services.llm.managers.database_chat_message_history"
            "._messages.Conversation",
            MagicMock(objects=conv_objects),
        ):
            meta = history.get_tool_call_metadata()

        assert len(meta) == 1, (
            "Expected 1 metadata entry, got %d" % len(meta)
        )
        assert meta[0]["metadata_type"] == "tool_calls"

    def test_recent_tool_names_skips_non_dict_entries(self) -> None:
        """recent_tool_names already had the guard — verify it works."""
        from airunner_services.llm.managers.database_chat_message_history import (
            DatabaseChatMessageHistory,
        )

        history = DatabaseChatMessageHistory.__new__(
            DatabaseChatMessageHistory
        )
        history.ephemeral = False
        history.logger = MagicMock()

        conv = MagicMock()
        conv.value = [
            "stray",
            {
                "metadata_type": "tool_calls",
                "tool_calls": [{"name": "search_news"}],
            },
        ]
        history._conversation = conv

        names = history.recent_tool_names(window=5)
        assert names == ["search_news"]

    def test_trim_orphaned_user_message_skips_non_dict(self) -> None:
        """trim_orphaned_user_message already had the guard — verify."""
        from airunner_services.llm.managers.database_chat_message_history import (
            DatabaseChatMessageHistory,
        )

        history = DatabaseChatMessageHistory.__new__(
            DatabaseChatMessageHistory
        )
        history.ephemeral = False
        history.logger = MagicMock()
        history.conversation_id = 1

        conv = MagicMock()
        conv.value = ["stray", {"role": "user", "content": "orphan"}]
        history._conversation = conv

        fake_update = MagicMock(return_value=True)
        conv_objects = MagicMock()
        conv_objects.update = fake_update

        with patch(
            "airunner_services.llm.managers.database_chat_message_history"
            "._session.Conversation",
            MagicMock(objects=conv_objects),
        ):
            history._trim_orphaned_user_message()

        # The orphaned user message should still be trimmed.
        assert len(conv.value) == 1, (
            "Expected 1 entry after trim, got %d" % len(conv.value)
        )


def test_messages_excludes_available_tools_metadata():
    """available_tools metadata entries are filtered from .messages.

    The ``messages`` property refreshes ``_conversation`` from the DB
    (``Conversation.objects.get``), so we must mock that call to return
    our test conversation with the ``available_tools`` entry.
    """
    from unittest.mock import MagicMock, patch

    from airunner_services.llm.managers.database_chat_message_history import (
        DatabaseChatMessageHistory,
    )

    history = DatabaseChatMessageHistory.__new__(DatabaseChatMessageHistory)
    history.logger = MagicMock()
    history.ephemeral = False
    history.conversation_id = 1
    # .messages checks `if not self._conversation: return []` before
    # refreshing from DB — give it a truthy placeholder so the refresh
    # (which we mock) executes.
    history._conversation = MagicMock()

    conv = MagicMock()
    conv.value = [
        {"role": "user", "content": "hello"},
        {
            "role": "system",
            "content": "Available tools: foo, bar",
            "metadata_type": "available_tools",
        },
        {"role": "assistant", "content": "hi!"},
    ]

    with patch(
        "airunner_services.llm.managers.database_chat_message_history"
        "._base.Conversation",
    ) as mock_conv_model:
        mock_conv_model.objects.get.return_value = conv
        msgs = history.messages

    assert len(msgs) == 2, (
        "Expected 2 messages (user + assistant), got %d" % len(msgs)
    )
    contents = [m.content for m in msgs]
    assert "Available tools" not in str(contents), (
        "available_tools entry leaked into LLM context"
    )


# ---------------------------------------------------------------------------
# Test: .messages reconstructs tool_calls / tool_result metadata entries
#        as real LangChain AIMessage(tool_calls=...) / ToolMessage objects
#        so the LLM has evidence a tool was called (amnesia bug fix).
# ---------------------------------------------------------------------------


def test_messages_reconstructs_tool_evidence():
    """tool_calls + tool_result entries become AIMessage + ToolMessage."""
    from unittest.mock import MagicMock, patch

    from airunner_services.llm.managers.database_chat_message_history import (
        DatabaseChatMessageHistory,
    )

    history = DatabaseChatMessageHistory.__new__(DatabaseChatMessageHistory)
    history.logger = MagicMock()
    history.ephemeral = False
    history.conversation_id = 1
    history._conversation = MagicMock()

    tool_call_id = "call_abc123"
    conv = MagicMock()
    conv.value = [
        {"role": "user", "content": "hello", "timestamp": ""},
        {
            "metadata_type": "tool_calls",
            "role": "tool_calls",
            "content": "Requested 1 tool(s): search_news",
            "tool_calls": [
                {"id": tool_call_id, "name": "search_news",
                 "args": {"query": "latest reviews"}},
            ],
        },
        {
            "metadata_type": "tool_result",
            "role": "tool_result",
            "content": "Great reviews overall.",
            "tool_call_id": tool_call_id,
        },
        {
            "role": "assistant",
            "content": "The reviews are great!",
            "timestamp": "",
        },
    ]

    with patch(
        "airunner_services.llm.managers.database_chat_message_history"
        "._base.Conversation",
    ) as mock_conv_model:
        mock_conv_model.objects.get.return_value = conv
        msgs = history.messages

    # Expected: [HumanMessage, AIMessage(tool_calls), ToolMessage, AIMessage]
    assert len(msgs) == 4, f"Expected 4 messages, got {len(msgs)}"

    # First: HumanMessage
    assert msgs[0].__class__.__name__ == "HumanMessage"
    assert msgs[0].content == "hello"

    # Second: AIMessage with tool_calls
    assert msgs[1].__class__.__name__ == "AIMessage"
    tool_calls = getattr(msgs[1], "tool_calls", None)
    assert tool_calls is not None, "AIMessage missing tool_calls"
    assert len(tool_calls) == 1
    assert tool_calls[0]["id"] == tool_call_id
    assert tool_calls[0]["name"] == "search_news"

    # Third: ToolMessage
    assert msgs[2].__class__.__name__ == "ToolMessage"
    assert msgs[2].content == "Great reviews overall."
    assert getattr(msgs[2], "tool_call_id", None) == tool_call_id

    # Fourth: final AIMessage
    assert msgs[3].__class__.__name__ == "AIMessage"
    assert msgs[3].content == "The reviews are great!"


def test_messages_still_skips_rag_injection_and_available_tools():
    """rag_injection/available_tools metadata is still filtered out."""
    from unittest.mock import MagicMock, patch

    from airunner_services.llm.managers.database_chat_message_history import (
        DatabaseChatMessageHistory,
    )

    history = DatabaseChatMessageHistory.__new__(DatabaseChatMessageHistory)
    history.logger = MagicMock()
    history.ephemeral = False
    history.conversation_id = 1
    history._conversation = MagicMock()

    conv = MagicMock()
    conv.value = [
        {"role": "user", "content": "hi", "timestamp": ""},
        {"metadata_type": "rag_injection", "content": "secret context"},
        {"metadata_type": "available_tools", "content": "tools: x, y"},
        {"role": "assistant", "content": "hello!", "timestamp": ""},
    ]

    with patch(
        "airunner_services.llm.managers.database_chat_message_history"
        "._base.Conversation",
    ) as mock_conv_model:
        mock_conv_model.objects.get.return_value = conv
        msgs = history.messages

    # Only user + assistant, no metadata leakage
    assert len(msgs) == 2, f"Expected 2, got {len(msgs)}"
    assert msgs[0].content == "hi"
    assert msgs[1].content == "hello!"
