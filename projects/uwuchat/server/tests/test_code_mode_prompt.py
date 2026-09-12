"""Unit tests for the code-mode system prompt (direct agent tools).

Asserts the code-mode prompt now advertises the inline headlesscode
proxy tools (execute_command, file read/edit, codebase_search,
run_tests) in addition to the existing launch_headlesscode_session
delegation guidance.
"""

from __future__ import annotations

from projects.uwuchat.server.code_mode_prompt import (
    code_mode_core_rules,
    code_mode_style,
    code_mode_topic_change_rule,
)


def test_core_rules_mention_direct_agent_tools() -> None:
    """The prompt names the inline proxy tools."""
    prompt = code_mode_core_rules()
    assert "execute_command" in prompt
    assert "read_file" in prompt
    assert "write_to_file" in prompt
    assert "codebase_search" in prompt
    assert "run_tests" in prompt
    assert "gh" in prompt


def test_core_rules_still_mention_session_launch() -> None:
    """The launch_headlesscode_session delegation path stays advertised."""
    prompt = code_mode_core_rules()
    assert "launch_headlesscode_session" in prompt


def test_core_rules_require_terminal_behavior() -> None:
    """The model must stop calling tools once it has the answer."""
    prompt = code_mode_core_rules()
    assert "STOP calling tools" in prompt
    assert "write the final answer in plain text" in prompt
    assert "do not call additional tools" in prompt


def test_core_rules_allow_multi_step_chaining() -> None:
    """Code mode must chain tools through a task, not stop after one."""
    prompt = code_mode_core_rules()
    assert "WORK THE TASK THROUGH" in prompt
    assert "keep calling tools until the whole task is done" in prompt
    # Anti-repetition intent is preserved: no redundant same-call re-runs.
    assert "Do NOT call the same tool again" in prompt
    # The contradictory one-result stop is gone.
    assert "STOP AFTER ONE RESULT" not in prompt
    assert "never another tool call" not in prompt


def test_core_rules_keep_companion_tool_ban() -> None:
    """Companion/platform tools remain banned in code mode."""
    prompt = code_mode_core_rules()
    assert "recall_knowledge" in prompt


def test_core_rules_explicit_github_access_via_execute_command() -> None:
    """The prompt must state gh IS available via execute_command.

    Regression: the local Qwen model kept claiming 'I don't have gh' and
    offering to web-search GitHub even though execute_command was bound.
    The prompt must counter that reflex explicitly.
    """
    prompt = code_mode_core_rules()
    assert "GITHUB ACCESS" in prompt
    assert "execute_command" in prompt
    assert "run `gh`" in prompt
    assert "Do NOT say 'I don't have gh'" in prompt
    assert "web-search" in prompt
    assert "gh issue view" in prompt


def test_style_returns_core_rules() -> None:
    """code_mode_style is the same content as the core rules."""
    assert code_mode_style() == code_mode_core_rules()


def test_topic_change_rule_empty() -> None:
    """Code mode has no topic-change directive."""
    assert code_mode_topic_change_rule() == ""
