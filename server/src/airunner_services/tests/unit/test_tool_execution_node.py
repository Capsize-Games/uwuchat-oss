"""Unit tests for ToolExecutionNodeMixin._execute_tools_with_status.

Covers the tool-execution orchestration: pass-through when there are
no tool calls, invalid-call dropping, duplicate interception, the
ToolNode execution path, synthetic ToolMessage injection, category
switch, and LRU recording — with all dependencies mocked.

The mixin reads helper methods that live on sibling mixins
(``_ensure_runtime_compat``, ``_get_forced_tool_policy``, etc.), so
the tests install them onto the instance with ``create=True`` patching.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)

# Must run the runtime compat shim before ToolNode is imported — the
# same convention as test_single_call_dedup_integration.py.  It makes
# the `from langgraph.prebuilt import ToolNode` inside
# _execute_tools_with_status resolve cleanly in this environment.
from airunner_services.llm.managers.mixins.tool_execution_mixin import (
    ToolExecutionMixin,
)
from airunner_services.llm.managers.mixins.tool_execution_mixin._execution import (
    ToolExecutionNodeMixin,
)
from airunner_services.llm.pii.vault import PIIVault

ToolExecutionMixin._ensure_runtime_compat()


class _Owner:
    """Minimal owner providing every attribute the mixin touches."""

    def __init__(self) -> None:
        self._tools = []
        self._executed_tools = []
        self.logger = MagicMock()


def _mixin(owner: _Owner) -> ToolExecutionNodeMixin:
    mixin = ToolExecutionNodeMixin()
    mixin.__dict__.update(owner.__dict__)
    return mixin


def _tool_call(name: str = "f", id: str = "tc-1") -> dict:
    return {"name": name, "args": {}, "id": id}


def _state(messages=None, **extra) -> dict:
    state = {"messages": messages or []}
    state.update(extra)
    return state


def _install_helpers(mixin, tool_calls, result_state=None) -> MagicMock:
    """Install the sibling-mixin helper methods + policy on *mixin*."""
    policy = MagicMock()
    policy.prepare.return_value = (
        _state([]), tool_calls, None,
    )
    mixin._get_forced_tool_policy = MagicMock(return_value=policy)
    mixin._ensure_tools_loaded = MagicMock()
    mixin._emit_starting_status = MagicMock()
    mixin._prebind_for_pending_category_switch = MagicMock()
    mixin._intercept_single_call_duplicates = MagicMock(
        return_value=(tool_calls, {})
    )
    mixin._emit_completed_status = MagicMock()
    mixin._stash_grounding_sources = MagicMock()
    mixin._handle_category_switch = MagicMock()
    mixin._record_tool_usage = MagicMock()
    return policy


# ---------------------------------------------------------------------------
# Early returns
# ---------------------------------------------------------------------------


def test_no_messages_passthrough() -> None:
    owner = _Owner()
    mixin = _mixin(owner)
    state = _state([])
    with patch.object(mixin, "_ensure_runtime_compat", create=True):
        assert mixin._execute_tools_with_status(state) is state


def test_no_tool_calls_passthrough() -> None:
    owner = _Owner()
    mixin = _mixin(owner)
    last = AIMessage(content="plain")
    state = _state([last])
    with patch.object(mixin, "_ensure_runtime_compat", create=True):
        assert mixin._execute_tools_with_status(state) is state


def test_empty_tool_calls_passthrough() -> None:
    owner = _Owner()
    mixin = _mixin(owner)
    last = AIMessage(content="", tool_calls=[])
    state = _state([last])
    with patch.object(mixin, "_ensure_runtime_compat", create=True):
        assert mixin._execute_tools_with_status(state) is state


def test_blocked_state_returned() -> None:
    owner = _Owner()
    mixin = _mixin(owner)
    last = AIMessage(content="", tool_calls=[_tool_call()])
    state = _state([last])
    blocked = {"messages": ["blocked"]}
    policy = MagicMock()
    policy.prepare.return_value = (
        state, [_tool_call()], blocked,
    )
    mixin._get_forced_tool_policy = MagicMock(return_value=policy)
    with patch.object(mixin, "_ensure_runtime_compat", create=True):
        assert mixin._execute_tools_with_status(state) is blocked


# ---------------------------------------------------------------------------
# Invalid tool call dropping
# ---------------------------------------------------------------------------


def test_drops_invalid_tool_calls() -> None:
    owner = _Owner()
    mixin = _mixin(owner)
    valid = _tool_call(name="keep", id="tc-1")
    bad_empty_name = {"name": "", "args": {}, "id": "tc-2"}
    bad_no_id = {"name": "x", "args": {}, "id": None}
    last = AIMessage(content="", tool_calls=[valid, bad_empty_name, bad_no_id])
    state = _state([last])

    policy = _install_helpers(
        mixin, [valid, bad_empty_name, bad_no_id],
    )
    policy.prepare.return_value = (state, [valid, bad_empty_name, bad_no_id], None)

    with patch.object(mixin, "_ensure_runtime_compat", create=True), patch(
        "langgraph.prebuilt.ToolNode"
    ) as tool_node_cls:
        node = MagicMock()
        node.invoke.return_value = {"messages": ["result"]}
        tool_node_cls.return_value = node
        with patch.object(
            mixin, "_refresh_grounding_cache_from_state", create=True
        ), patch.object(mixin, "_sanitize_tool_functions", create=True), patch(
            "airunner_services.llm.managers.mixins.tool_execution_mixin._execution.coerce_non_string_tool_args",
            lambda c: c,
        ):
            out = mixin._execute_tools_with_status(state)

    owner.logger.warning.assert_called_once()
    assert out is not None


# ---------------------------------------------------------------------------
# Full happy path
# ---------------------------------------------------------------------------


def test_full_execution_path() -> None:
    owner = _Owner()
    mixin = _mixin(owner)
    tc = _tool_call()
    last = AIMessage(content="", tool_calls=[tc])
    state = _state([last])

    policy = _install_helpers(mixin, [tc])
    policy.prepare.return_value = (state, [tc], None)

    with patch.object(mixin, "_ensure_runtime_compat", create=True), patch(
        "langgraph.prebuilt.ToolNode"
    ) as tool_node_cls:
        node = MagicMock()
        node.invoke.return_value = {"messages": ["tool-msg"]}
        tool_node_cls.return_value = node
        with patch.object(
            mixin, "_refresh_grounding_cache_from_state", create=True
        ), patch.object(mixin, "_sanitize_tool_functions", create=True), patch(
            "airunner_services.llm.managers.mixins.tool_execution_mixin._execution.coerce_non_string_tool_args",
            lambda c: c,
        ):
            out = mixin._execute_tools_with_status(state)

    mixin._emit_starting_status.assert_called_once()
    mixin._emit_completed_status.assert_called_once()
    mixin._stash_grounding_sources.assert_called_once()
    policy.complete.assert_called_once()
    mixin._handle_category_switch.assert_called_once()
    mixin._record_tool_usage.assert_called_once()
    assert out["messages"] == ["tool-msg"]


# ---------------------------------------------------------------------------
# Synthetic results + update_mood restore
# ---------------------------------------------------------------------------


def test_synthetic_results_injected() -> None:
    owner = _Owner()
    owner._executed_tools = ["update_mood"]
    mixin = _mixin(owner)
    tc = _tool_call()
    last = AIMessage(content="", tool_calls=[tc])
    state = _state([last])

    policy = _install_helpers(mixin, [tc])
    policy.prepare.return_value = (state, [tc], None)
    mixin._intercept_single_call_duplicates = MagicMock(
        return_value=([tc], {"tc-1": "synthetic"})
    )
    mixin._maybe_restore_mood_state = MagicMock()

    with patch.object(mixin, "_ensure_runtime_compat", create=True), patch(
        "langgraph.prebuilt.ToolNode"
    ) as tool_node_cls:
        node = MagicMock()
        node.invoke.return_value = {"messages": []}
        tool_node_cls.return_value = node
        with patch.object(
            mixin, "_refresh_grounding_cache_from_state", create=True
        ), patch.object(mixin, "_sanitize_tool_functions", create=True), patch(
            "airunner_services.llm.managers.mixins.tool_execution_mixin._execution.coerce_non_string_tool_args",
            lambda c: c,
        ):
            out = mixin._execute_tools_with_status(state)

    from langchain_core.messages import ToolMessage

    assert any(isinstance(m, ToolMessage) for m in out["messages"])
    mixin._maybe_restore_mood_state.assert_called_once()


# ---------------------------------------------------------------------------
# All duplicates intercepted → skip ToolNode
# ---------------------------------------------------------------------------


def test_all_duplicates_skips_tool_node() -> None:
    owner = _Owner()
    mixin = _mixin(owner)
    tc = _tool_call()
    last = AIMessage(content="", tool_calls=[tc])
    state = _state([last])

    policy = _install_helpers(mixin, [tc])
    policy.prepare.return_value = (state, [tc], None)
    mixin._intercept_single_call_duplicates = MagicMock(
        return_value=([], {"tc-1": "dup"})
    )

    with patch.object(mixin, "_ensure_runtime_compat", create=True), patch(
        "langgraph.prebuilt.ToolNode"
    ) as tool_node_cls:
        out = mixin._execute_tools_with_status(state)

    tool_node_cls.assert_not_called()
    from langchain_core.messages import ToolMessage

    assert any(isinstance(m, ToolMessage) for m in out["messages"])


# ---------------------------------------------------------------------------
# _record_search_tools_discoveries
# ---------------------------------------------------------------------------


def test_record_search_tools_discoveries() -> None:
    from langchain_core.messages import ToolMessage

    from airunner_services.llm.managers.mixins.tool_execution_mixin._execution import (
        _record_search_tools_discoveries,
    )

    owner = _Owner()
    owner._discovered_tools = set()
    tc = {"name": "search_tools", "args": {}, "id": "tc-1"}
    result_state = {
        "messages": [
            ToolMessage(
                content='{"tools": [{"name": "tool_a"}, {"name": "tool_b"}]}',
                tool_call_id="tc-1",
            )
        ]
    }
    _record_search_tools_discoveries(owner, [tc], result_state)
    assert owner._discovered_tools == {"tool_a", "tool_b"}


def test_record_search_tools_discoveries_bad_json() -> None:
    from langchain_core.messages import ToolMessage

    from airunner_services.llm.managers.mixins.tool_execution_mixin._execution import (
        _record_search_tools_discoveries,
    )

    owner = _Owner()
    owner._discovered_tools = set()
    tc = {"name": "search_tools", "args": {}, "id": "tc-1"}
    result_state = {
        "messages": [
            ToolMessage(content="{not json", tool_call_id="tc-1")
        ]
    }
    _record_search_tools_discoveries(owner, [tc], result_state)
    assert owner._discovered_tools == set()


def test_record_search_tools_skips_non_search_tool() -> None:
    """Non-search_tools calls are skipped (line 34 continue)."""
    from airunner_services.llm.managers.mixins.tool_execution_mixin._execution import (
        _record_search_tools_discoveries,
    )

    owner = _Owner()
    owner._discovered_tools = set()
    _record_search_tools_discoveries(
        owner, [{"name": "other", "args": {}, "id": "x"}], {"messages": []}
    )
    assert owner._discovered_tools == set()


def test_record_search_tools_skips_no_id() -> None:
    """A search_tools call with no id is skipped (line 37 continue)."""
    from airunner_services.llm.managers.mixins.tool_execution_mixin._execution import (
        _record_search_tools_discoveries,
    )

    owner = _Owner()
    owner._discovered_tools = set()
    _record_search_tools_discoveries(
        owner, [{"name": "search_tools", "args": {}, "id": None}],
        {"messages": []},
    )
    assert owner._discovered_tools == set()


def test_record_search_tools_no_matching_message() -> None:
    """No ToolMessage matches the id → nothing recorded (line 39->38)."""
    from airunner_services.llm.managers.mixins.tool_execution_mixin._execution import (
        _record_search_tools_discoveries,
    )

    owner = _Owner()
    owner._discovered_tools = set()
    tc = {"name": "search_tools", "args": {}, "id": "tc-1"}
    _record_search_tools_discoveries(
        owner, [tc], {"messages": ["not a ToolMessage"]}
    )
    assert owner._discovered_tools == set()


def test_record_search_tools_skips_empty_names() -> None:
    """Entries without a name are skipped (line 47->45)."""
    from langchain_core.messages import ToolMessage

    from airunner_services.llm.managers.mixins.tool_execution_mixin._execution import (
        _record_search_tools_discoveries,
    )

    owner = _Owner()
    owner._discovered_tools = set()
    tc = {"name": "search_tools", "args": {}, "id": "tc-1"}
    result_state = {
        "messages": [
            ToolMessage(
                content='{"tools": [{"name": ""}, {}]}',
                tool_call_id="tc-1",
            )
        ]
    }
    _record_search_tools_discoveries(owner, [tc], result_state)
    assert owner._discovered_tools == set()


def test_all_invalid_tool_calls_returns_state() -> None:
    """When every tool call is invalid, the original state is returned."""
    owner = _Owner()
    mixin = _mixin(owner)
    bad = {"name": "", "args": {}, "id": None}
    last = AIMessage(content="", tool_calls=[bad])
    state = _state([last])

    policy = _install_helpers(mixin, [bad])
    policy.prepare.return_value = (state, [bad], None)

    with patch.object(mixin, "_ensure_runtime_compat", create=True):
        out = mixin._execute_tools_with_status(state)

    assert out is state
    owner.logger.warning.assert_called_once()


# ---------------------------------------------------------------------------
# _restore_tool_result_pii
# ---------------------------------------------------------------------------


def test_restore_tool_result_pii_restores_placeholders() -> None:
    """ToolMessage placeholders are restored from the PII vault."""
    vault = PIIVault()
    vault.placeholder_for("EMAIL", "user@example.com")
    vault.placeholder_for("PASSWORD", "example-lan-password")

    owner = _Owner()
    owner._pii_vault = vault
    mixin = _mixin(owner)

    state = _state([
        ToolMessage(
            content=(
                'File: plans/parallel-tasks/w16-continue2.md\n'
                '{"email":"[EMAIL_1]","password":"[PASSWORD_1]"}'
            ),
            tool_call_id="tc-1",
        ),
    ])
    out = mixin._restore_tool_result_pii(state)

    restored = out["messages"][0].content
    assert "user@example.com" in restored
    assert "example-lan-password" in restored
    assert "[EMAIL_1]" not in restored
    assert "[PASSWORD_1]" not in restored


def test_restore_tool_result_pii_no_vault_is_noop() -> None:
    """Without a vault the state passes through unchanged."""
    owner = _Owner()
    owner._pii_vault = None
    mixin = _mixin(owner)

    msg = ToolMessage(content="plain result", tool_call_id="tc-1")
    state = _state([msg])
    out = mixin._restore_tool_result_pii(state)

    assert out is state
    assert out["messages"][0] is msg


def test_restore_tool_result_pii_skips_non_tool_messages() -> None:
    """AIMessage/HumanMessage content is left untouched."""
    vault = PIIVault()
    vault.placeholder_for("PERSON", "Alice")

    owner = _Owner()
    owner._pii_vault = vault
    mixin = _mixin(owner)

    ai = AIMessage(content="[PERSON_1]", tool_calls=[])
    hm = HumanMessage(content="hi [PERSON_1]")
    tm = ToolMessage(content="[PERSON_1]", tool_call_id="tc-1")
    out = mixin._restore_tool_result_pii(_state([ai, hm, tm]))

    assert out["messages"][0].content == "[PERSON_1]"
    assert out["messages"][1].content == "hi [PERSON_1]"
    assert out["messages"][2].content == "Alice"
