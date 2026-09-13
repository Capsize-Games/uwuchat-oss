"""Tests for tool-name propagation in rolling_compressor.

Validates that ``_session_messages`` annotates assistant messages with
``tool_names`` from preceding ``tool_calls`` metadata entries, and that
``_build_compression_prompt`` renders them without leaking full tool
result content.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helper: build a fake Conversation row with the given value list.
# ---------------------------------------------------------------------------


def _fake_conversations(value_entries: list[dict]) -> list[MagicMock]:
    """Return a list with one MagicMock Conversation whose .value is
    *value_entries*."""
    conv = MagicMock()
    conv.value = value_entries
    return [conv]


def _mock_session_messages(
    mock_conv_model: MagicMock,
    entries: list[dict],
) -> list[MagicMock]:
    """Configure the mock Conversation chain and return fake rows."""
    fake = _fake_conversations(entries)
    mock_conv_model.objects.query.return_value.filter.return_value \
        .order_by.return_value.all.return_value = fake
    return fake


# ---------------------------------------------------------------------------
# _session_messages
# ---------------------------------------------------------------------------


class TestSessionMessagesToolNames:
    """_session_messages annotates assistant turns with tool_names."""

    def test_assistant_after_tool_call_gets_tool_names(self) -> None:
        with patch(
            "airunner_services.database.models.conversation.Conversation",
        ) as mock_conv_model:
            _mock_session_messages(mock_conv_model, [
                {"role": "user", "content": "what are the reviews?"},
                {
                    "metadata_type": "tool_calls",
                    "tool_calls": [{"name": "search_news"}],
                },
                {
                    "metadata_type": "tool_result",
                    "content": "FULL SEARCH RESULT -- raw data",
                    "tool_call_id": "abc",
                },
                {"role": "assistant", "content": "The reviews are great!"},
            ])

            from airunner_services.llm.rolling_compressor import (
                _session_messages,
            )

            msgs = _session_messages(session_id=1)

        # user + assistant (metadata excluded)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1].get("tool_names") == ["search_news"], (
            f"Expected ['search_news'], got {msgs[1].get('tool_names')}"
        )

    def test_multiple_tool_calls_accumulate_names(self) -> None:
        with patch(
            "airunner_services.database.models.conversation.Conversation",
        ) as mock_conv_model:
            _mock_session_messages(mock_conv_model, [
                {"role": "user", "content": "x"},
                {
                    "metadata_type": "tool_calls",
                    "tool_calls": [{"name": "search_news"}],
                },
                {"role": "assistant", "content": "a"},
                {"role": "user", "content": "y"},
                {
                    "metadata_type": "tool_calls",
                    "tool_calls": [
                        {"name": "search_news"},
                        {"name": "weather_current"},
                    ],
                },
                {"role": "assistant", "content": "b"},
            ])

            from airunner_services.llm.rolling_compressor import (
                _session_messages,
            )

            msgs = _session_messages(session_id=1)

        assert msgs[1]["tool_names"] == ["search_news"]
        # Second assistant gets both tools called on that turn
        assert msgs[3]["tool_names"] == [
            "search_news", "weather_current",
        ]

    def test_user_message_does_not_get_tool_names(self) -> None:
        with patch(
            "airunner_services.database.models.conversation.Conversation",
        ) as mock_conv_model:
            _mock_session_messages(mock_conv_model, [
                {
                    "metadata_type": "tool_calls",
                    "tool_calls": [{"name": "search_news"}],
                },
                {"role": "user", "content": "follow up"},
            ])

            from airunner_services.llm.rolling_compressor import (
                _session_messages,
            )

            msgs = _session_messages(session_id=1)

        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert "tool_names" not in msgs[0]

    def test_rag_injection_and_proactive_trigger_still_excluded(
        self,
    ) -> None:
        with patch(
            "airunner_services.database.models.conversation.Conversation",
        ) as mock_conv_model:
            _mock_session_messages(mock_conv_model, [
                {"role": "user", "content": "hi"},
                {"metadata_type": "rag_injection", "content": "ctx"},
                {"metadata_type": "proactive_trigger", "content": "x"},
                {"role": "assistant", "content": "hello"},
            ])

            from airunner_services.llm.rolling_compressor import (
                _session_messages,
            )

            msgs = _session_messages(session_id=1)

        assert len(msgs) == 2
        contents = [m["content"] for m in msgs]
        assert "ctx" not in contents
        assert "x" not in contents


# ---------------------------------------------------------------------------
# _build_compression_prompt
# ---------------------------------------------------------------------------


class TestBuildCompressionPromptToolNames:
    """_build_compression_prompt renders tool_names without leaking results."""

    def test_tool_names_appear_in_prompt(self) -> None:
        from airunner_services.llm.rolling_compressor import (
            _build_compression_prompt,
        )

        msgs = [
            {"role": "user", "content": "what are the reviews?"},
            {
                "role": "assistant",
                "content": "The reviews are great!",
                "tool_names": ["search_news"],
            },
        ]

        prompt = _build_compression_prompt("TestBot", msgs)

        assert "[used tools: search_news]" in prompt, (
            f"tool annotation missing from prompt:\n{prompt}"
        )

    def test_full_tool_result_not_in_prompt(self) -> None:
        from airunner_services.llm.rolling_compressor import (
            _build_compression_prompt,
        )

        msgs = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "done",
                "tool_names": ["search_news"],
            },
        ]

        prompt = _build_compression_prompt("TestBot", msgs)

        # Tool result content is excluded by _session_messages; the
        # prompt builder only sees tool_names, never raw result content.
        assert "FULL SEARCH RESULT" not in prompt
        assert "5000 chars" not in prompt

    def test_message_without_tool_names_has_no_annotation(self) -> None:
        from airunner_services.llm.rolling_compressor import (
            _build_compression_prompt,
        )

        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

        prompt = _build_compression_prompt("TestBot", msgs)

        assert "[used tools:" not in prompt, (
            "tool annotation should not appear for non-tool messages"
        )
        assert "hello" in prompt
        assert "hi there" in prompt
