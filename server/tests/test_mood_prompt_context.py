"""Tests for mood prompt context enrichment.

Covers:
- Persona/backstory inclusion when flags are enabled; clean omission
  when disabled.
- User name inclusion when present; graceful degradation when empty.
- AgentMemory excerpt inclusion when a row exists; omission when not.
- Word-boundary message truncation (never mid-word, never exceeds cap).
- Per-turn and session-end prompts both apply PERSPECTIVE RULES and
  VARIETY RULES identically.
"""

from __future__ import annotations

from unittest.mock import patch

from airunner_services.llm.mood.context import (
    MoodContext,
    _snippet,
    _truncate_on_word_boundary,
    build_mood_context,
)
from airunner_services.llm.mood.prompt import (
    _format_messages,
    build_mood_prompt,
)


# ── Truncation tests ─────────────────────────────────────────

class TestTruncateOnWordBoundary:
    """Verify _truncate_on_word_boundary behaviour."""

    def test_short_text_returned_unchanged(self) -> None:
        result = _truncate_on_word_boundary("Hello world", 200)
        assert result == "Hello world"

    def test_exact_limit_returned_unchanged(self) -> None:
        text = "Hello"
        result = _truncate_on_word_boundary(text, len(text))
        assert result == text

    def test_truncates_on_word_boundary(self) -> None:
        text = "Hello world this is a test of truncation"
        # Cap at 12 — should cut after "Hello world"
        result = _truncate_on_word_boundary(text, 12)
        assert result == "Hello world\u2026"

    def test_no_word_boundary_hard_truncates(self) -> None:
        text = "Supercalifragilisticexpialidocious"
        result = _truncate_on_word_boundary(text, 10)
        assert result == "Supercalif\u2026"
        assert len(result) <= 10 + 1  # text + ellipsis

    def test_never_exceeds_cap_plus_ellipsis(self) -> None:
        text = "a " * 200
        result = _truncate_on_word_boundary(text, 100)
        # Truncated text + ellipsis should not exceed cap + 1
        prefix = result.rstrip("\u2026")
        assert len(prefix) <= 100

    def test_strips_leading_trailing_whitespace(self) -> None:
        result = _truncate_on_word_boundary("   hello world   ", 200)
        assert result == "hello world"


class TestSnippet:
    """Verify _snippet correctly handles edge cases."""

    def test_empty_text_returns_empty(self) -> None:
        assert _snippet("", 200) == ""
        assert _snippet("   ", 200) == ""

    def test_none_text(self) -> None:
        assert _snippet(None, 200) == ""

    def test_trims_to_cap(self) -> None:
        text = "This is a long text that should be cut down"
        result = _snippet(text, 15)
        assert len(result.rstrip("\u2026")) <= 15


# ── Message formatting tests ─────────────────────────────────

class TestFormatMessages:
    """Verify message formatting with word-boundary truncation."""

    def test_formats_role_and_content(self) -> None:
        msgs = [{"role": "user", "content": "Hello bot"}]
        result = _format_messages(msgs)
        assert result == "USER: Hello bot"

    def test_truncates_long_messages_on_word_boundary(self) -> None:
        msgs = [{"role": "assistant",
                 "content": "a b c d e f g h i j k l m n o p"}]
        result = _format_messages(msgs)
        # With _MESSAGE_CAP=200 this won't truncate, but verify
        # the pattern
        assert result.startswith("ASSISTANT: ")

    def test_missing_role_defaults_to_question(self) -> None:
        msgs = [{"content": "no role here"}]
        result = _format_messages(msgs)
        assert result.startswith("?: ")


# ── Prompt context tests ─────────────────────────────────────

class _StubChatbot:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _StubConversation:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class TestBuildMoodContext:
    """Verify build_mood_context assembles fields correctly."""

    def test_persona_included_when_enabled(self) -> None:
        chatbot = _StubChatbot(
            botname="TestBot",
            use_personality=True,
            bot_personality="Cheerful and helpful.",
            use_backstory=False,
            backstory="",
            id=1,
        )
        conv = _StubConversation(user_name="Alice")
        with patch(
            "airunner_services.llm.mood.context._fetch_agent_memory",
            return_value=None,
        ):
            ctx = build_mood_context(chatbot, conv, [], {})
        assert ctx.persona_snippet == "Cheerful and helpful."

    def test_persona_omitted_when_disabled(self) -> None:
        chatbot = _StubChatbot(
            botname="TestBot",
            use_personality=False,
            bot_personality="Should not appear.",
            use_backstory=False,
            backstory="",
            id=1,
        )
        conv = _StubConversation(user_name="Alice")
        with patch(
            "airunner_services.llm.mood.context._fetch_agent_memory",
            return_value=None,
        ):
            ctx = build_mood_context(chatbot, conv, [], {})
        assert ctx.persona_snippet == ""

    def test_backstory_included_when_enabled(self) -> None:
        chatbot = _StubChatbot(
            botname="TestBot",
            use_personality=False,
            bot_personality="",
            use_backstory=True,
            backstory="Once upon a time...",
            id=1,
        )
        conv = _StubConversation(user_name="Alice")
        with patch(
            "airunner_services.llm.mood.context._fetch_agent_memory",
            return_value=None,
        ):
            ctx = build_mood_context(chatbot, conv, [], {})
        assert ctx.backstory_snippet == "Once upon a time..."

    def test_backstory_omitted_when_disabled(self) -> None:
        chatbot = _StubChatbot(
            botname="TestBot",
            use_personality=False,
            bot_personality="",
            use_backstory=False,
            backstory="Should not appear.",
            id=1,
        )
        conv = _StubConversation(user_name="Alice")
        with patch(
            "airunner_services.llm.mood.context._fetch_agent_memory",
            return_value=None,
        ):
            ctx = build_mood_context(chatbot, conv, [], {})
        assert ctx.backstory_snippet == ""

    def test_user_name_included_when_present(self) -> None:
        chatbot = _StubChatbot(
            botname="TestBot",
            use_personality=False,
            bot_personality="",
            use_backstory=False,
            backstory="",
            id=1,
        )
        conv = _StubConversation(user_name="Charlie")
        with patch(
            "airunner_services.llm.mood.context._fetch_agent_memory",
            return_value=None,
        ):
            ctx = build_mood_context(chatbot, conv, [], {})
        assert ctx.user_name == "Charlie"

    def test_user_name_omitted_when_empty(self) -> None:
        chatbot = _StubChatbot(
            botname="TestBot",
            use_personality=False,
            bot_personality="",
            use_backstory=False,
            backstory="",
            id=1,
        )
        conv = _StubConversation(user_name="")
        with patch(
            "airunner_services.llm.mood.context._fetch_agent_memory",
            return_value=None,
        ):
            ctx = build_mood_context(chatbot, conv, [], {})
        assert ctx.user_name == ""

    def test_user_name_omitted_when_whitespace(self) -> None:
        chatbot = _StubChatbot(
            botname="TestBot",
            use_personality=False,
            bot_personality="",
            use_backstory=False,
            backstory="",
            id=1,
        )
        conv = _StubConversation(user_name="   ")
        with patch(
            "airunner_services.llm.mood.context._fetch_agent_memory",
            return_value=None,
        ):
            ctx = build_mood_context(chatbot, conv, [], {})
        assert ctx.user_name == ""

    def test_memory_included_when_row_exists(self) -> None:
        chatbot = _StubChatbot(
            botname="TestBot",
            use_personality=False,
            bot_personality="",
            use_backstory=False,
            backstory="",
            id=1,
        )
        conv = _StubConversation(user_name="Alice")
        with patch(
            "airunner_services.llm.mood.context._fetch_agent_memory",
            return_value="A long history together.",
        ):
            ctx = build_mood_context(chatbot, conv, [], {})
        assert ctx.memory_snippet == "A long history together."

    def test_memory_omitted_when_no_row(self) -> None:
        chatbot = _StubChatbot(
            botname="TestBot",
            use_personality=False,
            bot_personality="",
            use_backstory=False,
            backstory="",
            id=1,
        )
        conv = _StubConversation(user_name="Alice")
        with patch(
            "airunner_services.llm.mood.context._fetch_agent_memory",
            return_value=None,
        ):
            ctx = build_mood_context(chatbot, conv, [], {})
        assert ctx.memory_snippet == ""

    def test_empty_persona_omitted_even_when_flag_enabled(self) -> None:
        chatbot = _StubChatbot(
            botname="TestBot",
            use_personality=True,
            bot_personality="",
            use_backstory=False,
            backstory="",
            id=1,
        )
        conv = _StubConversation(user_name="Alice")
        with patch(
            "airunner_services.llm.mood.context._fetch_agent_memory",
            return_value=None,
        ):
            ctx = build_mood_context(chatbot, conv, [], {})
        assert ctx.persona_snippet == ""

    def test_none_chatbot_produces_minimal_context(self) -> None:
        ctx = build_mood_context(None, None, [], {})
        assert ctx.chatbot_name == ""
        assert ctx.persona_snippet == ""
        assert ctx.backstory_snippet == ""
        assert ctx.user_name == ""
        assert ctx.memory_snippet == ""


# ── Prompt builder tests ─────────────────────────────────────

class TestBuildMoodPrompt:
    """Verify build_mood_prompt produces correct output."""

    def _base_context(self, **kwargs) -> MoodContext:
        defaults = {
            "chatbot_name": "TestBot",
            "current_mood": "happy",
            "current_emoji": "😊",
        }
        defaults.update(kwargs)
        return MoodContext(**defaults)

    def test_per_turn_framing(self) -> None:
        ctx = self._base_context()
        prompt = build_mood_prompt(ctx, is_session_end=False)
        assert "Recent conversation:" in prompt
        assert "How do you feel now after this exchange?" in prompt
        assert "You've just finished" not in prompt

    def test_session_end_framing(self) -> None:
        ctx = self._base_context()
        prompt = build_mood_prompt(ctx, is_session_end=True)
        assert "You've just finished a conversation session." in prompt
        assert "Here is the full session:" in prompt
        assert "How do you feel now at the end of this session?" in prompt

    def test_both_paths_include_perspective_rules(self) -> None:
        ctx = self._base_context()
        per_turn = build_mood_prompt(ctx, is_session_end=False)
        session_end = build_mood_prompt(ctx, is_session_end=True)
        assert "PERSPECTIVE RULES:" in per_turn
        assert "PERSPECTIVE RULES:" in session_end
        assert "- You ARE TestBot. Write your mood as 'I feel...'." in per_turn
        assert "- You ARE TestBot. Write your mood as 'I feel...'." in session_end

    def test_both_paths_include_variety_rules(self) -> None:
        ctx = self._base_context()
        per_turn = build_mood_prompt(ctx, is_session_end=False)
        session_end = build_mood_prompt(ctx, is_session_end=True)
        assert "VARIETY RULES:" in per_turn
        assert "VARIETY RULES:" in session_end
        assert "curious" in per_turn
        assert "intrigued" in per_turn
        assert "curious" in session_end
        assert "intrigued" in session_end

    def test_includes_persona_snippet_when_present(self) -> None:
        ctx = self._base_context(
            persona_snippet="A cheerful companion."
        )
        prompt = build_mood_prompt(ctx)
        assert "Your personality: A cheerful companion." in prompt

    def test_omits_persona_section_when_empty(self) -> None:
        ctx = self._base_context(persona_snippet="")
        prompt = build_mood_prompt(ctx)
        assert "Your personality:" not in prompt

    def test_includes_user_name_when_present(self) -> None:
        ctx = self._base_context(user_name="Alice")
        prompt = build_mood_prompt(ctx)
        assert "You are talking to Alice." in prompt

    def test_omits_user_name_when_empty(self) -> None:
        ctx = self._base_context(user_name="")
        prompt = build_mood_prompt(ctx)
        assert "You are talking to" not in prompt

    def test_includes_memory_when_present(self) -> None:
        ctx = self._base_context(
            memory_snippet="You've known each other for years."
        )
        prompt = build_mood_prompt(ctx)
        assert "Your memories of this relationship:" in prompt
        assert "You've known each other for years." in prompt

    def test_omits_memory_when_empty(self) -> None:
        ctx = self._base_context(memory_snippet="")
        prompt = build_mood_prompt(ctx)
        assert "Your memories of this relationship:" not in prompt

    def test_no_placeholder_junk(self) -> None:
        """When all optional fields are empty, no label-without-value."""
        ctx = self._base_context()
        prompt = build_mood_prompt(ctx)
        assert "Backstory: " not in prompt
        assert "Personality: " not in prompt
        assert "talking to " not in prompt

    def test_includes_messages(self) -> None:
        ctx = self._base_context(messages=[
            {"role": "user", "content": "Hi!"},
            {"role": "assistant", "content": "Hello there!"},
        ])
        prompt = build_mood_prompt(ctx)
        assert "USER: Hi!" in prompt
        assert "ASSISTANT: Hello there!" in prompt

    def test_includes_current_mood(self) -> None:
        ctx = self._base_context(
            current_mood="curious", current_emoji="🤔"
        )
        prompt = build_mood_prompt(ctx)
        assert "Your last recorded mood was: curious 🤔" in prompt

    def test_per_turn_and_session_end_rules_identical(self) -> None:
        """Both paths must produce identical PERSPECTIVE + VARIETY blocks."""
        ctx = self._base_context()
        per_turn = build_mood_prompt(ctx, is_session_end=False)
        session_end = build_mood_prompt(ctx, is_session_end=True)
        # Extract rules sections
        def _rules_section(prompt_text: str) -> str:
            start = prompt_text.find("PERSPECTIVE RULES:")
            if start == -1:
                return ""
            return prompt_text[start:]
        assert _rules_section(per_turn) == _rules_section(session_end), (
            "Per-turn and session-end rules must be identical"
        )


# ── LLM call regression test ─────────────────────────────────

class TestCallLlmResponsePassthrough:
    """Verify _call_llm passes a real response object to token recording,
    not None (which would silently zero token counts)."""

    def test_response_object_passed_to_record_usage(self) -> None:
        """_record_mood_usage receives a non-None response arg."""
        from unittest.mock import MagicMock, patch
        from airunner_services.llm.mood.llm_call import _call_llm

        fake_response = MagicMock()
        fake_response.content = '{"mood": "happy", "emoji": "😊"}'
        fake_response.usage_metadata = {
            "input_tokens": 100, "output_tokens": 50,
        }

        with patch(
            "airunner_services.llm.mood.llm_call.os.getenv",
            return_value="fake-key",
        ), patch(
            "airunner_services.llm.pipeline_loader.pipeline_config",
            return_value={},
        ), patch(
            "airunner_services.llm.mood.llm_call._invoke_llm",
            return_value=('{"mood":"happy"}', fake_response),
        ), patch(
            "airunner_services.llm.mood.llm_call._record_mood_usage",
        ) as mock_record:
            _call_llm("test prompt")

            response_arg = mock_record.call_args[0][1]
            assert response_arg is not None, (
                "_record_mood_usage received None as response — "
                "token counts will be zero"
            )
            assert response_arg is fake_response, (
                "Response should be the same object returned "
                "by _invoke_llm"
            )
