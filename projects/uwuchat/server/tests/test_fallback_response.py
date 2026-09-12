"""Tests for the UwUChat fallback response override.

Verifies that the in-character fallback message never exposes raw
tool names and that the framework's ``_tool_only_fallback`` respects
the project override when it is importable.
"""

from __future__ import annotations

# The full code-mode tool set from issue #155.  Every name must
# trigger the code-mode fallback line, never the generic one, and
# must never be exposed verbatim in the returned message.
_CODE_MODE_TOOL_NAMES = (
    "apply_diff",
    "codebase_search",
    "edit_file",
    "execute_command",
    "launch_headlesscode_session",
    "list_files",
    "list_registered_projects",
    "read_file",
    "run_tests",
    "search_replace",
    "write_to_file",
)


class TestUwuchatFallbackResponse:
    """Unit tests for uwuchat_fallback_response()."""

    @staticmethod
    def _uwuchat_fallback(executed_tools: list[str]) -> str:
        """Import-under-test helper."""
        from projects.uwuchat.server.fallback_response import (
            uwuchat_fallback_response,
        )
        return uwuchat_fallback_response(executed_tools)

    # ── in-character message ─────────────────────────────────────

    def test_returns_nonempty_string(self) -> None:
        """The override always returns a non-empty fallback."""
        result = self._uwuchat_fallback(["search_fastsearch"])
        assert isinstance(result, str)
        assert len(result) > 0

    def test_never_exposes_tool_names(self) -> None:
        """The fallback must never mention raw tool names."""
        result = self._uwuchat_fallback(
            ["search_fastsearch", "check_grounding"]
        )
        assert "search_fastsearch" not in result
        assert "check_grounding" not in result
        assert "search_news" not in result

    def test_does_not_contain_diagnostic_language(self) -> None:
        """The fallback must not contain framework diagnostic phrasing."""
        result = self._uwuchat_fallback(
            ["search_fastsearch", "check_grounding"]
        )
        assert "non-mutating" not in result.lower()
        assert "read-only" not in result.lower()
        assert "tool" not in result.lower()
        assert "did not produce" not in result.lower()

    def test_empty_tool_list_is_handled(self) -> None:
        """An empty tool list still produces a reasonable message."""
        result = self._uwuchat_fallback([])
        assert isinstance(result, str)
        assert len(result) > 0
        assert "tool" not in result.lower()

    # ── code-mode tool sets ──────────────────────────────────────

    def test_code_mode_tool_returns_code_mode_line(self) -> None:
        """execute_command triggers the code-mode fallback line."""
        result = self._uwuchat_fallback(["execute_command"])
        assert "I tried to run that" in result
        assert "execute_command" not in result

    def test_code_mode_file_tools_use_code_mode_line(self) -> None:
        """A code-mode file tool also triggers the code-mode line."""
        result = self._uwuchat_fallback(["read_file"])
        assert "I tried to run that" in result
        assert "read_file" not in result

    def test_generic_tools_keep_generic_line(self) -> None:
        """Non-code tools keep the generic in-character line."""
        result = self._uwuchat_fallback(["search_fastsearch"])
        assert "looked into that" in result
        assert "I tried to run that" not in result

    def test_code_mode_line_never_exposes_tool_names(self) -> None:
        """The code-mode line never names any code tool."""
        result = self._uwuchat_fallback(
            ["execute_command", "read_file", "write_to_file"]
        )
        for name in ("execute_command", "read_file", "write_to_file"):
            assert name not in result

    def test_every_code_mode_tool_triggers_code_mode_line(self) -> None:
        """Every code-mode tool name triggers the code-mode line."""
        for name in _CODE_MODE_TOOL_NAMES:
            result = self._uwuchat_fallback([name])
            assert "I tried to run that" in result
            assert name not in result

    def test_code_mode_tool_set_matches_expected_names(self) -> None:
        """The module's code-mode set is exactly the enumerated names."""
        from projects.uwuchat.server.fallback_response import (
            _CODE_MODE_TOOLS,
        )
        assert set(_CODE_MODE_TOOLS) == set(_CODE_MODE_TOOL_NAMES)


class TestFrameworkToolOnlyFallback:
    """Unit tests for _tool_only_fallback() and the project override."""

    @staticmethod
    def _tool_only_fallback(effective_tools: list[str]) -> str:
        """Import-under-test helper for the framework function."""
        from airunner_services.llm.managers.mixins import (
            generation_response_support,
        )
        return generation_response_support._tool_only_fallback(
            effective_tools
        )

    @staticmethod
    def _framework_tool_fallback(effective_tools: list[str]) -> str:
        """Import-under-test helper for the framework-default function."""
        from airunner_services.llm.managers.mixins import (
            generation_response_support,
        )
        return generation_response_support._framework_tool_fallback(
            effective_tools
        )

    # ── project override is present ──────────────────────────────

    def test_uwuchat_override_is_used_when_module_is_present(
        self,
    ) -> None:
        """When the UwUChat module is importable, its message is used."""
        result = self._tool_only_fallback(
            ["search_fastsearch", "check_grounding"]
        )
        assert "tool" not in result.lower()
        assert "search_fastsearch" not in result
        assert len(result) > 0

    # ── status-only tools produce empty ──────────────────────────

    def test_status_only_tools_return_empty(self) -> None:
        """Tools in STATUS_ONLY_TOOLS produce an empty fallback."""
        result = self._tool_only_fallback(["update_mood"])
        assert result == ""

    # ── framework-default fallback is still correct ──────────────

    def test_framework_read_only_fallback_still_works(self) -> None:
        """The framework read-only fallback returns the correct text."""
        result = self._framework_tool_fallback(
            ["read_code_file", "search_files"]
        )
        assert "read-only" in result.lower()
        assert "read_code_file" in result
        assert "search_files" in result

    def test_framework_non_mutating_fallback_still_works(self) -> None:
        """The framework non-mutating fallback returns the correct text."""
        result = self._framework_tool_fallback(
            ["search_fastsearch", "check_grounding"]
        )
        assert "non-mutating" in result.lower()
        assert "search_fastsearch" in result
        assert "check_grounding" in result

    def test_framework_mutating_fallback_still_works(self) -> None:
        """The framework mutating-tool fallback returns the correct text."""
        result = self._framework_tool_fallback(
            ["create_code_file", "run_tests"]
        )
        assert "tool actions" in result.lower()
        assert "create_code_file" in result
        assert "run_tests" in result


class TestFallbackResponseForEmptyResult:
    """Integration-level tests for fallback_response_for_empty_result()."""

    @staticmethod
    def _fallback_for_empty(
        result: dict,
        executed_tools: list[str],
    ) -> str:
        """Import-under-test helper."""
        from airunner_services.llm.managers.mixins import (
            generation_response_support,
        )
        return generation_response_support.fallback_response_for_empty_result(
            result, executed_tools
        )

    def test_tool_only_case_uses_project_override(self) -> None:
        """When tools were executed but no text, project override is used."""
        result = self._fallback_for_empty(
            {"messages": []},
            ["search_fastsearch", "check_grounding"],
        )
        assert "tool" not in result.lower()
        assert "search_fastsearch" not in result
        assert len(result) > 0

    def test_empty_messages_with_tool_calls_in_ai_messages(
        self,
    ) -> None:
        """AIMessages with tool_calls but no content use the fallback."""
        from langchain_core.messages import AIMessage

        ai_msg = AIMessage(content="", tool_calls=[])
        ai_msg.tool_calls = [{"name": "search_fastsearch", "args": {}}]
        result = self._fallback_for_empty(
            {"messages": [ai_msg]},
            [],
        )
        assert "tool" not in result.lower()
        assert "search_fastsearch" not in result
        assert len(result) > 0

    def test_no_tools_no_ai_messages_returns_empty(self) -> None:
        """When nothing happened at all, return empty string."""
        result = self._fallback_for_empty(
            {"messages": []},
            [],
        )
        assert result == ""

    def test_ai_message_with_empty_content_only(self) -> None:
        """An AIMessage with no tools and no content returns a message."""
        from langchain_core.messages import AIMessage

        result = self._fallback_for_empty(
            {"messages": [AIMessage(content="")]},
            [],
        )
        assert len(result) > 0
