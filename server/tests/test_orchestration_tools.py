"""Tests for the orchestration meta-tools: list_tool_categories and
switch_tool_category."""

from __future__ import annotations

import json
from unittest.mock import patch

from airunner_services.llm.core.tool_registry import (
    ToolCategory,
    ToolRegistry,
)


# =========================================================================
# list_tool_categories
# =========================================================================


def test_list_tool_categories_includes_enabled_categories() -> None:
    """list_tool_categories returns category names with descriptions."""
    from airunner_services.llm.tools.orchestration_tools import (
        list_tool_categories,
    )

    result = json.loads(list_tool_categories())
    names = {c["name"] for c in result["categories"]}
    assert "system" in names
    assert "math" in names
    assert "knowledge" in names
    assert "mood" in names
    # Every category entry must have a non-empty description
    for cat in result["categories"]:
        assert cat["description"], (
            f"Category '{cat['name']}' has empty description"
        )


def test_list_tool_categories_excludes_disabled() -> None:
    """Disabled categories do not appear in list_tool_categories output."""
    from airunner_services.llm.tools.orchestration_tools import (
        list_tool_categories,
    )

    with patch(
        "airunner_services.llm.tools.orchestration_tools._disabled_categories",
        return_value={"image", "author"},
    ):
        result = json.loads(list_tool_categories())
        names = {c["name"] for c in result["categories"]}
        assert "image" not in names
        assert "author" not in names
        assert "system" in names


# =========================================================================
# switch_tool_category
# =========================================================================


def test_switch_tool_category_valid() -> None:
    """switch_tool_category with a valid enabled category returns success."""
    from airunner_services.llm.tools.orchestration_tools import (
        switch_tool_category,
    )

    result = json.loads(switch_tool_category("math"))
    assert result["success"] is True
    assert result["category"] == "math"


def test_switch_tool_category_invalid() -> None:
    """switch_tool_category with a nonexistent category returns error."""
    from airunner_services.llm.tools.orchestration_tools import (
        switch_tool_category,
    )

    result = json.loads(switch_tool_category("nonexistent_category_xyz"))
    assert result["success"] is False
    assert "Unknown or disabled category" in result["error"]


def test_switch_tool_category_disabled() -> None:
    """switch_tool_category with a disabled category returns error."""
    from airunner_services.llm.tools.orchestration_tools import (
        switch_tool_category,
    )

    with patch(
        "airunner_services.llm.tools.orchestration_tools._disabled_categories",
        return_value={"image"},
    ):
        result = json.loads(switch_tool_category("image"))
        assert result["success"] is False
        assert "Unknown or disabled category" in result["error"]
        assert "image" in result["error"]


def test_switch_tool_category_empty() -> None:
    """switch_tool_category with empty input returns error."""
    from airunner_services.llm.tools.orchestration_tools import (
        switch_tool_category,
    )

    result = json.loads(switch_tool_category(""))
    assert result["success"] is False
    assert "No category name provided" in result["error"]


# =========================================================================
# Orchestration tools are registered
# =========================================================================


def test_orchestration_tools_registered() -> None:
    """Both orchestration tools are present in ToolRegistry."""
    assert ToolRegistry.get("list_tool_categories") is not None
    assert ToolRegistry.get("switch_tool_category") is not None


def test_orchestration_tools_in_correct_category() -> None:
    """Both orchestration tools belong to ToolCategory.ORCHESTRATION."""
    list_info = ToolRegistry.get("list_tool_categories")
    switch_info = ToolRegistry.get("switch_tool_category")
    assert list_info is not None
    assert switch_info is not None
    assert list_info.category == ToolCategory.ORCHESTRATION
    assert switch_info.category == ToolCategory.ORCHESTRATION


# =========================================================================
# ALWAYS_INCLUDE_CATEGORIES
# =========================================================================


def test_orchestration_in_always_include_categories() -> None:
    """ToolClassificationMixin always-include set has orchestration."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert (
        "orchestration"
        in ToolClassificationMixin.ALWAYS_INCLUDE_CATEGORIES
    )


# =========================================================================
# _handle_category_switch rebind
# =========================================================================


def test_handle_category_switch_rebinds_tools() -> None:
    """_rebind_for_category replaces tools and rebinds the model."""
    from unittest.mock import MagicMock

    from airunner_services.llm.managers.mixins.tool_execution_mixin \
        import ToolExecutionMixin

    host = MagicMock()
    host.logger = MagicMock()
    host._tool_manager = MagicMock()
    host._tools = [MagicMock()]
    host._unbind_tools_from_model = MagicMock()
    host._bind_tools_to_model = MagicMock()

    fake_knowledge_tool = MagicMock()
    fake_knowledge_tool.name = "recall_knowledge"
    fake_list_tool = MagicMock()
    fake_list_tool.name = "list_tool_categories"
    fake_switch_tool = MagicMock()
    fake_switch_tool.name = "switch_tool_category"

    def get_tools_side_effect(categories, **__):
        if categories == [ToolCategory.KNOWLEDGE]:
            return [fake_knowledge_tool]
        if categories == [ToolCategory.ORCHESTRATION]:
            return [fake_list_tool, fake_switch_tool]
        return []

    host._tool_manager.get_tools_by_categories = MagicMock(
        side_effect=get_tools_side_effect,
    )

    ToolExecutionMixin._rebind_for_category(
        host, ToolCategory.KNOWLEDGE,
    )

    host._unbind_tools_from_model.assert_called_once()
    host._bind_tools_to_model.assert_called_once()
    tool_names = {t.name for t in host._tools}
    assert "recall_knowledge" in tool_names
    assert "list_tool_categories" in tool_names
    # switch_tool_category is stripped on success
    assert "switch_tool_category" not in tool_names


def test_handle_category_switch_skips_failed_switch() -> None:
    """_handle_category_switch does nothing when switch_tool_category fails."""
    from unittest.mock import MagicMock

    import airunner_services.llm.managers.mixins.tool_execution_mixin \
        as tem

    host = MagicMock()
    host.logger = MagicMock()
    host._tool_manager = MagicMock()

    tool_calls = [
        {"name": "switch_tool_category", "id": "call_1", "args": {}},
    ]
    from langchain_core.messages import ToolMessage

    result_state = {
        "messages": [
            ToolMessage(
                content=json.dumps({
                    "success": False,
                    "error": "bad category",
                }),
                tool_call_id="call_1",
            ),
        ],
    }

    tem.ToolExecutionMixin._handle_category_switch(
        host, tool_calls, result_state,
    )

    host._tool_manager.get_tools_by_categories.assert_not_called()


# =========================================================================
# End-to-end: wrong initial category → switch → recovery
# =========================================================================


def test_auto_select_with_orchestration_always_present() -> None:
    """When auto_select picks a category, orchestration is included later."""
    from airunner_services.llm.managers.mixins.tool_filtering_mixin import (
        ToolFilteringMixin,
    )
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    class Host(ToolFilteringMixin, ToolClassificationMixin):
        ALWAYS_INCLUDE_CATEGORIES = {"mood", "orchestration"}

        def __init__(self) -> None:
            import logging
            self.logger = logging.getLogger("test")
            self._workflow_manager = None
            self._tool_manager = None

    host = Host()
    with patch.object(
        host, "_classify_prompt_for_tools", return_value=["math"]
    ), patch.object(host, "_emit_tool_selection_status"):
        categories, _force = host._auto_select_tool_categories(
            "calculate the derivative of x^2",
        )
        assert "math" in categories
        assert "orchestration" not in categories, (
            "orchestration should not be in the classified set — it is "
            "added later via _normalize_tool_categories"
        )

    effective = host._normalize_tool_categories(["math"])
    assert "math" in effective
    assert "orchestration" in effective
    assert "mood" in effective


def test_end_to_end_misclassification_recovery() -> None:
    """Mis-categorized prompt → switch → target tool becomes available.

    Simulates the original bug's shape: the keyword heuristic picks the
    wrong category (search for a 'recently in my email' query), the
    model calls switch_tool_category('knowledge'), and afterward a
    knowledge tool (recall_knowledge) is present in the bound tools.
    """
    from unittest.mock import MagicMock

    from airunner_services.llm.managers.mixins.tool_execution_mixin \
        import ToolExecutionMixin

    host = MagicMock()
    host.logger = MagicMock()
    host._tool_manager = MagicMock()
    host._unbind_tools_from_model = MagicMock()
    host._bind_tools_to_model = MagicMock()
    host._tools = []

    fake_knowledge_tool = MagicMock()
    fake_knowledge_tool.name = "search_email_knowledge"
    fake_list = MagicMock()
    fake_list.name = "list_tool_categories"
    fake_switch = MagicMock()
    fake_switch.name = "switch_tool_category"

    def get_tools(categories, **__):
        if categories == [ToolCategory.KNOWLEDGE]:
            return [fake_knowledge_tool]
        if categories == [ToolCategory.ORCHESTRATION]:
            return [fake_list, fake_switch]
        return []

    host._tool_manager.get_tools_by_categories = MagicMock(
        side_effect=get_tools,
    )

    from langchain_core.messages import ToolMessage

    tool_calls = [
        {"name": "switch_tool_category", "id": "c1", "args": {}},
    ]
    result_state = {
        "messages": [
            ToolMessage(
                content=json.dumps({
                    "success": True,
                    "category": "knowledge",
                }),
                tool_call_id="c1",
            ),
        ],
    }

    # Pre-condition: no tools are bound yet
    assert tool_names(host._tools) == set()

    host._rebind_for_category = (
        lambda cat: ToolExecutionMixin._rebind_for_category(host, cat)
    )
    ToolExecutionMixin._handle_category_switch(
        host, tool_calls, result_state,
    )

    # Post-condition: knowledge tool is bound, switch tool is stripped
    names = tool_names(host._tools)
    assert "search_email_knowledge" in names, (
        f"Expected search_email_knowledge in tools, got: {names}"
    )
    assert "switch_tool_category" not in names


def test_switch_tool_category_survives_failed_call() -> None:
    """Failed switch_tool_category is still callable for retry.

    After a failed call (typo, disabled category), dedup must NOT strip
    switch_tool_category from self._tools — it should remain available
    so the model can retry with a corrected name in the same turn.
    """
    from unittest.mock import MagicMock

    from airunner_services.llm.managers.mixins.tool_execution_mixin \
        import ToolExecutionMixin

    host = MagicMock()
    host.logger = MagicMock()
    host._tool_manager = MagicMock()
    host._unbind_tools_from_model = MagicMock()
    host._bind_tools_to_model = MagicMock()
    host._executed_tools = ["switch_tool_category"]

    fake_switch = MagicMock()
    fake_switch.name = "switch_tool_category"
    fake_list = MagicMock()
    fake_list.name = "list_tool_categories"
    host._tools = [fake_switch, fake_list]

    from langchain_core.messages import ToolMessage

    tool_calls = [
        {"name": "switch_tool_category", "id": "c1", "args": {}},
    ]
    result_state = {
        "messages": [
            ToolMessage(
                content=json.dumps({
                    "success": False,
                    "error": "bad category",
                }),
                tool_call_id="c1",
            ),
        ],
    }

    # Run dedup first (simulates the real execution order)
    ToolExecutionMixin._deduplicate_executed_tools(host)

    # Then run _handle_category_switch (no-op for failed switch)
    ToolExecutionMixin._handle_category_switch(
        host, tool_calls, result_state,
    )

    # switch_tool_category must still be present for retry
    names = tool_names(host._tools)
    assert "switch_tool_category" in names, (
        f"switch_tool_category was stripped after failed call! "
        f"Remaining: {names}"
    )
    assert "list_tool_categories" in names


def test_switch_tool_category_retry_after_failed_call() -> None:
    """Failed switch → retry with corrected name succeeds same turn.

    After a typo/d failure, the model can retry switch_tool_category
    with the correct name and have it take effect within the same turn.
    """
    from unittest.mock import MagicMock

    from airunner_services.llm.managers.mixins.tool_execution_mixin \
        import ToolExecutionMixin

    host = MagicMock()
    host.logger = MagicMock()
    host._tool_manager = MagicMock()
    host._unbind_tools_from_model = MagicMock()
    host._bind_tools_to_model = MagicMock()
    host._executed_tools = []

    fake_knowledge_tool = MagicMock()
    fake_knowledge_tool.name = "recall_knowledge"
    fake_list = MagicMock()
    fake_list.name = "list_tool_categories"
    fake_switch = MagicMock()
    fake_switch.name = "switch_tool_category"
    host._tools = [fake_switch, fake_list]

    def get_tools(categories, **__):
        if categories == [ToolCategory.KNOWLEDGE]:
            return [fake_knowledge_tool]
        if categories == [ToolCategory.ORCHESTRATION]:
            return [fake_list, fake_switch]
        return []

    host._tool_manager.get_tools_by_categories = MagicMock(
        side_effect=get_tools,
    )

    host._rebind_for_category = (
        lambda cat: ToolExecutionMixin._rebind_for_category(host, cat)
    )

    from langchain_core.messages import ToolMessage

    # Cycle 1: failed switch (typo)
    ToolExecutionMixin._deduplicate_executed_tools(host)
    ToolExecutionMixin._handle_category_switch(
        host,
        [{"name": "switch_tool_category", "id": "c1", "args": {}}],
        {
            "messages": [
                ToolMessage(
                    content=json.dumps(
                        {"success": False, "error": "typo"}
                    ),
                    tool_call_id="c1",
                ),
            ],
        },
    )
    assert "switch_tool_category" in tool_names(host._tools)

    # Cycle 2: successful switch (corrected name)
    host._executed_tools = ["switch_tool_category"]
    ToolExecutionMixin._deduplicate_executed_tools(host)
    ToolExecutionMixin._handle_category_switch(
        host,
        [{"name": "switch_tool_category", "id": "c2", "args": {}}],
        {
            "messages": [
                ToolMessage(
                    content=json.dumps({
                        "success": True,
                        "category": "knowledge",
                    }),
                    tool_call_id="c2",
                ),
            ],
        },
    )

    names = tool_names(host._tools)
    assert "recall_knowledge" in names, (
        f"Expected recall_knowledge after retry, got: {names}"
    )
    assert "switch_tool_category" not in names


def tool_names(tools: list) -> set:
    """Return the set of tool names from a list of mock/real tools."""
    return {
        getattr(t, "name", getattr(t, "__name__", None))
        for t in tools
    }


# =========================================================================
# Same-turn switch + target tool (Root Cause 1 reproduction)
# =========================================================================


def test_prebind_for_pending_category_switch_updates_tools() -> None:
    """_prebind_for_pending_category_switch rebinds before ToolNode.

    When the model emits switch_tool_category + a knowledge tool in the
    same AIMessage batch, the prebind method must update self._tools
    to include the target category tools before ToolNode is built,
    while keeping switch_tool_category itself available for execution.
    """
    from unittest.mock import MagicMock

    from airunner_services.llm.managers.mixins.tool_execution_mixin \
        import ToolExecutionMixin
    from airunner_services.llm.core.tool_registry import ToolCategory

    host = MagicMock()
    host.logger = MagicMock()
    host._tool_manager = MagicMock()
    host._unbind_tools_from_model = MagicMock()
    host._bind_tools_to_model = MagicMock()

    fake_knowledge_tool = MagicMock()
    fake_knowledge_tool.name = "record_knowledge"
    fake_list = MagicMock()
    fake_list.name = "list_tool_categories"
    fake_switch = MagicMock()
    fake_switch.name = "switch_tool_category"
    host._tools = [fake_switch, fake_list]

    def get_tools(categories, **__):
        if categories == [ToolCategory.KNOWLEDGE]:
            return [fake_knowledge_tool]
        if categories == [ToolCategory.ORCHESTRATION]:
            return [fake_list, fake_switch]
        return []

    host._tool_manager.get_tools_by_categories = MagicMock(
        side_effect=get_tools,
    )

    # Bind the real _rebind_for_category so the prebind can call it.
    host._rebind_for_category = (
        lambda cat, keep_switch=False: ToolExecutionMixin
        ._rebind_for_category(host, cat, keep_switch=keep_switch)
    )

    tool_calls = [
        {"name": "switch_tool_category", "id": "c1",
         "args": {"category": "knowledge"}},
        {"name": "record_knowledge", "id": "c2",
         "args": {"fact": "test"}},
    ]

    ToolExecutionMixin._prebind_for_pending_category_switch(
        host, tool_calls,
    )

    names = tool_names(host._tools)
    assert "record_knowledge" in names, (
        f"Expected record_knowledge in tools after prebind, got: {names}"
    )
    assert "switch_tool_category" in names, (
        "switch_tool_category must remain available so ToolNode can "
        "execute it and produce its ToolMessage"
    )
    assert "list_tool_categories" in names


def test_prebind_skips_when_no_switch_call() -> None:
    """_prebind_for_pending_category_switch is a no-op without switch."""
    from unittest.mock import MagicMock

    from airunner_services.llm.managers.mixins.tool_execution_mixin \
        import ToolExecutionMixin

    host = MagicMock()
    host._tool_manager = MagicMock()
    host._tools = [MagicMock()]

    tool_calls = [
        {"name": "record_knowledge", "id": "c1",
         "args": {"fact": "test"}},
    ]

    ToolExecutionMixin._prebind_for_pending_category_switch(
        host, tool_calls,
    )

    host._tool_manager.get_tools_by_categories.assert_not_called()


def test_prebind_skips_failed_switch() -> None:
    """_prebind_for_pending_category_switch ignores failed switches."""
    from unittest.mock import MagicMock

    from airunner_services.llm.managers.mixins.tool_execution_mixin \
        import ToolExecutionMixin

    host = MagicMock()
    host.logger = MagicMock()
    host._tool_manager = MagicMock()
    host._tools = [MagicMock()]

    tool_calls = [
        {"name": "switch_tool_category", "id": "c1",
         "args": {"category": "nonexistent_xyz"}},
        {"name": "record_knowledge", "id": "c2",
         "args": {"fact": "test"}},
    ]

    ToolExecutionMixin._prebind_for_pending_category_switch(
        host, tool_calls,
    )

    host._tool_manager.get_tools_by_categories.assert_not_called()


def test_prebind_sanitization_runs_on_rebound_tools() -> None:
    """_sanitize_tool_functions runs on tools swapped in by prebind.

    _sanitize_tool_functions must run AFTER
    _prebind_for_pending_category_switch so that freshly-rebound
    target-category tools pass through sanitization.
    A tool without __doc__ or description would raise ValueError inside
    ToolNode when LangChain wraps it via StructuredTool.from_function.
    """
    from unittest.mock import MagicMock

    from airunner_services.llm.managers.mixins.tool_execution_mixin \
        import ToolExecutionMixin
    from airunner_services.llm.core.tool_registry import ToolCategory

    host = MagicMock()
    host.logger = MagicMock()
    host._tool_manager = MagicMock()
    host._unbind_tools_from_model = MagicMock()
    host._bind_tools_to_model = MagicMock()

    # Target-category tool: no __doc__, no description — must be sanitized.
    undoc_tool = MagicMock()
    undoc_tool.name = "record_knowledge"
    undoc_tool.__name__ = "record_knowledge"
    undoc_tool.__doc__ = None
    # Delete the description attribute so sanitize uses the auto-generated
    # fallback string.
    del undoc_tool.description

    fake_list = MagicMock()
    fake_list.name = "list_tool_categories"
    fake_switch = MagicMock()
    fake_switch.name = "switch_tool_category"
    host._tools = [fake_switch, fake_list]

    def get_tools(categories, **__):
        if categories == [ToolCategory.KNOWLEDGE]:
            return [undoc_tool]
        if categories == [ToolCategory.ORCHESTRATION]:
            return [fake_list, fake_switch]
        return []

    host._tool_manager.get_tools_by_categories = MagicMock(
        side_effect=get_tools,
    )
    host._rebind_for_category = (
        lambda cat, keep_switch=False: ToolExecutionMixin
        ._rebind_for_category(host, cat, keep_switch=keep_switch)
    )

    # Prebind swaps in the undoc_tool.
    ToolExecutionMixin._prebind_for_pending_category_switch(
        host,
        [{"name": "switch_tool_category", "id": "c1",
          "args": {"category": "knowledge"}}],
    )
    names = tool_names(host._tools)
    assert "record_knowledge" in names
    assert undoc_tool.__doc__ is None, (
        "undoc_tool should still be undocumented before sanitization"
    )

    # Sanitize — this is what the reordered _execute_tools_with_status
    # now calls AFTER prebind.
    ToolExecutionMixin._sanitize_tool_functions(host)

    assert undoc_tool.__doc__ is not None, (
        "undoc_tool should have a docstring after sanitization"
    )
    assert "Tool function 'record_knowledge'" in undoc_tool.__doc__, (
        f"Expected auto-generated docstring, got: {undoc_tool.__doc__!r}"
    )


def test_prebind_then_handle_strips_switch_keeps_target() -> None:
    """Full sequence: prebind → handle_category_switch strips switch tool.

    After a same-turn switch, switch_tool_category must be stripped from
    self._tools (it just did its job), while the target-category tools
    and list_tool_categories remain bound for the next model turn.
    """
    from unittest.mock import MagicMock

    from langchain_core.messages import ToolMessage

    from airunner_services.llm.managers.mixins.tool_execution_mixin \
        import ToolExecutionMixin
    from airunner_services.llm.core.tool_registry import ToolCategory

    host = MagicMock()
    host.logger = MagicMock()
    host._tool_manager = MagicMock()
    host._unbind_tools_from_model = MagicMock()
    host._bind_tools_to_model = MagicMock()
    host._prebound_switch_ids = set()

    fake_knowledge_tool = MagicMock()
    fake_knowledge_tool.name = "record_knowledge"
    fake_list = MagicMock()
    fake_list.name = "list_tool_categories"
    fake_switch = MagicMock()
    fake_switch.name = "switch_tool_category"
    host._tools = [fake_switch, fake_list]

    def get_tools(categories, **__):
        if categories == [ToolCategory.KNOWLEDGE]:
            return [fake_knowledge_tool]
        if categories == [ToolCategory.ORCHESTRATION]:
            return [fake_list, fake_switch]
        return []

    host._tool_manager.get_tools_by_categories = MagicMock(
        side_effect=get_tools,
    )
    host._rebind_for_category = (
        lambda cat, keep_switch=False: ToolExecutionMixin
        ._rebind_for_category(host, cat, keep_switch=keep_switch)
    )

    # Step 1: prebind (same-turn switch to knowledge)
    tool_calls = [
        {"name": "switch_tool_category", "id": "c1",
         "args": {"category": "knowledge"}},
        {"name": "record_knowledge", "id": "c2",
         "args": {"fact": "test"}},
    ]
    ToolExecutionMixin._prebind_for_pending_category_switch(
        host, tool_calls,
    )

    # After prebind: all three tools present (switch kept for ToolNode)
    names = tool_names(host._tools)
    assert "switch_tool_category" in names, (
        "switch_tool_category should be present after prebind"
    )
    assert "record_knowledge" in names
    assert "list_tool_categories" in names

    # Step 2: simulate ToolNode result — successful switch
    result_state = {
        "messages": [
            ToolMessage(
                content=json.dumps({
                    "success": True,
                    "category": "knowledge",
                }),
                tool_call_id="c1",
            ),
        ],
    }

    # Step 3: handle_category_switch should strip switch, keep the rest
    ToolExecutionMixin._handle_category_switch(
        host, tool_calls, result_state,
    )

    names = tool_names(host._tools)
    assert "switch_tool_category" not in names, (
        f"switch_tool_category must be stripped after successful switch, "
        f"got: {names}"
    )
    assert "record_knowledge" in names, (
        f"record_knowledge must remain after switch, got: {names}"
    )
    assert "list_tool_categories" in names, (
        f"list_tool_categories must remain after switch, got: {names}"
    )
