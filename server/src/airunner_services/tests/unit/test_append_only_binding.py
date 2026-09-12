"""Tests for append-only tool binding via _ensure_tools_loaded.

Verifies that discovered tools are appended without removing prior
tools, and that repeated searches accumulate rather than replacing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestEnsureToolsLoaded:
    """Tests for _ensure_tools_loaded append-only behavior."""

    @staticmethod
    def _make_owner(existing_tool_names: list[str] | None = None):
        """Build a mock owner with configured _tools list."""
        owner = MagicMock()
        # Create StructuredTool-like mocks with .name attribute
        if existing_tool_names:
            owner._tools = [
                MagicMock(name=name) for name in existing_tool_names
            ]
            for t, name in zip(owner._tools, existing_tool_names):
                t.name = name
        else:
            owner._tools = []
        owner._discovered_tools = set()
        owner._bind_tools_to_model = MagicMock()
        owner.logger = MagicMock()
        return owner

    @staticmethod
    def _call(owner: MagicMock, tool_calls: list[dict]) -> None:
        from airunner_services.llm.managers.mixins.tool_execution_mixin \
            import ToolExecutionMixin
        ToolExecutionMixin._ensure_tools_loaded(owner, tool_calls)

    # ── append behavior ─────────────────────────────────────────

    def test_appends_discovered_tool(self) -> None:
        """A discovered tool is appended to existing tools."""
        owner = self._make_owner(["update_mood", "search_tools"])
        owner._discovered_tools.add("search_fastsearch_news")

        from airunner_services.llm.core.tool_registry import ToolInfo
        from airunner_services.llm.core.tool_registry import ToolCategory

        fake_info = ToolInfo(
            name="search_fastsearch_news",
            func=lambda q: f"result for {q}",
            category=ToolCategory.RESEARCH,
            description="Search news articles",
            return_direct=False,
        )

        with patch(
            "airunner_services.llm.core.tool_registry.ToolRegistry.get",
            return_value=fake_info,
        ):
            self._call(
                owner,
                [{"name": "search_fastsearch_news", "id": "call_1"}],
            )

        tool_names = [
            t.name for t in owner._tools
        ]
        assert tool_names == [
            "update_mood", "search_tools", "search_fastsearch_news",
        ], f"Expected append, got {tool_names}"

    def test_does_not_duplicate_existing_tool(self) -> None:
        """A tool already in self._tools is not appended again."""
        owner = self._make_owner(["update_mood", "search_news"])
        owner._discovered_tools.add("search_news")

        self._call(
            owner,
            [{"name": "search_news", "id": "call_1"}],
        )

        tool_names = [t.name for t in owner._tools]
        assert tool_names == ["update_mood", "search_news"]
        # Should not rebind since nothing was added
        owner._bind_tools_to_model.assert_not_called()

    def test_multiple_discoveries_accumulate(self) -> None:
        """Multiple calls to _ensure_tools_loaded accumulate tools."""
        owner = self._make_owner(["search_tools"])

        from airunner_services.llm.core.tool_registry import ToolInfo
        from airunner_services.llm.core.tool_registry import ToolCategory

        fake_tools = {
            "search_fastsearch_news": ToolInfo(
                name="search_fastsearch_news",
                func=lambda q: q,
                category=ToolCategory.RESEARCH,
                description="A",
                return_direct=False,
            ),
            "scrape_website": ToolInfo(
                name="scrape_website",
                func=lambda u: u,
                category=ToolCategory.RESEARCH,
                description="B",
                return_direct=False,
            ),
        }

        def _get(name):
            return fake_tools.get(name)

        with patch(
            "airunner_services.llm.core.tool_registry.ToolRegistry.get",
            side_effect=_get,
        ):
            # First discovery
            owner._discovered_tools.add("search_fastsearch_news")
            self._call(
                owner,
                [{"name": "search_fastsearch_news", "id": "c1"}],
            )

            # Second discovery
            owner._discovered_tools.add("scrape_website")
            self._call(
                owner,
                [{"name": "scrape_website", "id": "c2"}],
            )

        tool_names = [t.name for t in owner._tools]
        assert tool_names == [
            "search_tools", "search_fastsearch_news", "scrape_website",
        ], f"Expected accumulation, got {tool_names}"

    def test_rebinds_after_appending(self) -> None:
        """After appending a new tool, _bind_tools_to_model is called."""
        owner = self._make_owner(["search_tools"])
        owner._discovered_tools.add("calculator")

        from airunner_services.llm.core.tool_registry import ToolInfo
        from airunner_services.llm.core.tool_registry import ToolCategory

        fake_info = ToolInfo(
            name="calculator",
            func=lambda e: eval(e),
            category=ToolCategory.MATH,
            description="Evaluate math",
            return_direct=False,
        )

        with patch(
            "airunner_services.llm.core.tool_registry.ToolRegistry.get",
            return_value=fake_info,
        ):
            self._call(
                owner,
                [{"name": "calculator", "id": "call_1"}],
            )

        owner._bind_tools_to_model.assert_called_once()

    def test_no_rebind_when_nothing_new(self) -> None:
        """When no new tools are loaded, rebind is not called."""
        owner = self._make_owner(["search_tools"])
        # Only existing tools requested — nothing to load
        self._call(
            owner,
            [{"name": "search_tools", "id": "call_1"}],
        )
        owner._bind_tools_to_model.assert_not_called()

    # ── rejection of undiscovered tools ─────────────────────────

    def test_rejects_tool_not_in_discovered_set(self) -> None:
        """A tool name not in _discovered_tools is rejected."""
        owner = self._make_owner(["search_tools"])
        # NOT adding to _discovered_tools

        self._call(
            owner,
            [{"name": "some_hallucinated_tool", "id": "call_1"}],
        )

        # Should not be added
        tool_names = [t.name for t in owner._tools]
        assert "some_hallucinated_tool" not in tool_names
        owner.logger.warning.assert_called()


class TestOrchestrationHint:
    """Tests for the updated orchestration hint prompt."""

    def test_prompt_references_search_tools(self) -> None:
        """The prompt tells the model to use search_tools."""
        from airunner_services.llm.managers.prompt_builder.orchestration_hint \
            import ORCHESTRATION_INSTRUCTIONS

        assert "search_tools" in ORCHESTRATION_INSTRUCTIONS
        assert "list_tool_categories" not in ORCHESTRATION_INSTRUCTIONS
        assert "switch_tool_category" not in ORCHESTRATION_INSTRUCTIONS

    def test_prompt_explains_discovery(self) -> None:
        """The prompt explains that search_tools finds and binds tools."""
        from airunner_services.llm.managers.prompt_builder.orchestration_hint \
            import ORCHESTRATION_INSTRUCTIONS

        assert "find matching tools" in ORCHESTRATION_INSTRUCTIONS
        assert "make them available" in ORCHESTRATION_INSTRUCTIONS

    def test_hint_function_returns_prompt_when_tools_bound(self) -> None:
        """orchestration_hint_part returns the prompt when tools exist."""
        from airunner_services.llm.managers.prompt_builder.orchestration_hint \
            import orchestration_hint_part

        owner = MagicMock()
        owner._tools = [MagicMock()]
        result = orchestration_hint_part(owner)
        assert result is not None
        assert "search_tools" in result

    def test_hint_function_returns_none_when_no_tools(self) -> None:
        """orchestration_hint_part returns None when no tools bound."""
        from airunner_services.llm.managers.prompt_builder.orchestration_hint \
            import orchestration_hint_part

        owner = MagicMock()
        owner._tools = []
        result = orchestration_hint_part(owner)
        assert result is None
