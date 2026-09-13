"""Regression test: UwUChat's own tools (journal, calendar, task,
weather, email) must register on the same eager path as framework
tools, not only the never-firing lazy-reload fallback.

Context: ``ToolManager`` eagerly imports the framework's tool package
(``from airunner_services.llm import tools`` in tool_manager.py),
registering framework tools as an import side effect before anything
else runs. That means ``ToolRegistry._ensure_default_tools_loaded()``'s
"registry is completely empty" fallback — the only mechanism that
would have imported ``projects.uwuchat.server.tools`` — never fires
again for the life of the process, since the registry always already
has framework tools in it by the time anything asks. Confirmed live:
every UwUChat-specific tool (calendar reminders, task tracking,
journal entries, weather, and the new email-knowledge tool) was
silently absent from the running daemon's registry despite being
correctly registered in every isolated throwaway-script test — the
isolated tests looked correct because a fresh script's import order
differs from the real app's.
"""

from __future__ import annotations


class TestProjectToolsRegisterOnImportOrder:
    def test_uwuchat_tools_present_after_tool_manager_import(self) -> None:
        """Reproduce the real app's import order: ToolManager first
        (as any LLM manager construction does), then inspect the
        registry — mirrors exactly what was broken live."""
        from airunner_services.llm.core.tool_registry import (
            ToolCategory,
            ToolRegistry,
        )
        from airunner_services.llm.tool_manager import ToolManager

        assert ToolManager is not None  # import triggers registration

        recall_names = {
            t.name
            for t in ToolRegistry._categories.get(ToolCategory.RECALL, [])
        }
        assert "search_conversations" in recall_names, (
            "sanity check: framework tool must still register"
        )
        assert "search_email_knowledge" in recall_names, (
            "project tool must register on the same eager path as "
            "framework tools, not only the unreachable lazy fallback"
        )

    def test_other_uwuchat_productivity_tools_also_present(self) -> None:
        """This bug silently broke calendar/task/journal/weather tools
        too, not just email — guard all of them together."""
        from airunner_services.llm.core.tool_registry import ToolRegistry
        from airunner_services.llm.tool_manager import ToolManager

        assert ToolManager is not None  # import triggers registration

        expected = {
            "write_journal_entry",
            "add_calendar_event",
            "remember_task",
            "get_my_weather",
            "search_email_knowledge",
        }
        registered = set(ToolRegistry._tools.keys())
        missing = expected - registered
        assert not missing, f"Tools never registered: {missing}"
