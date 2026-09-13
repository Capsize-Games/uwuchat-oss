"""Tests for the tool-name collision precedence fix in ToolRegistry.

The registry stores ONE entry per tool name (``_tools[name]``).  The
framework's lazy reload loop (``_ensure_default_tools_loaded``) re-runs
``importlib.reload`` on every built-in tool module whenever a
missing-name/category lookup happens, re-registering framework tools
over the active project's overrides.  The live failure: UwUChat's
code-mode ``read_file`` proxy (CODE category, routes to the headlesscode
harness) was clobbered by the framework's FILE-category ``read_file``
(reads the server container's filesystem), so every code-mode
``read_file`` failed with "File does not exist".

The fix: registration carries source precedence (project > extension >
framework); a lower-precedence registration never replaces a
higher-precedence one, and stale entries are purged from every category
list so ``get_by_category`` never returns a non-winning copy.

These tests are deliberately SELF-CONTAINED: they register tools under
unique names and clean up after themselves, never clearing or reloading
the shared registry (which would disturb other test modules that rely on
the registry's pre-populated state).
"""

from __future__ import annotations

import pytest

from airunner_services.llm.core.tool_registry import (
    ToolCategory,
    ToolRegistry,
    _TOOL_SOURCE_PRECEDENCE,
    _tool_source,
)

# Names used by the fake registrations below.  Kept unique per test so
# tests never collide with real registered tools.
_REGISTERED_NAMES: set[str] = set()


def _make_func(module: str):
    """Build a callable attributed to *module* via setattr.

    ``__module__`` is a normal writable attribute at runtime; setting it
    through ``setattr`` avoids any type-checker noise and matches how the
    registry classifies real tool functions.
    """
    def fake_tool() -> str:  # pragma: no cover - never invoked
        return "ok"

    setattr(fake_tool, "__module__", module)
    return fake_tool


def _register_fake(
    name: str,
    module: str,
    category: ToolCategory,
    *,
    description: str = "fake tool",
    requires_agent: bool = False,
    defer_loading: bool = False,
) -> ToolRegistry:
    """Register a fake tool function attributed to *module* and return it."""
    fake_tool = _make_func(module)
    ToolRegistry.register(
        name=name,
        category=category,
        description=description,
        requires_agent=requires_agent,
        defer_loading=defer_loading,
    )(fake_tool)
    _REGISTERED_NAMES.add(name)
    return fake_tool


@pytest.fixture(autouse=True)
def _cleanup_fakes() -> None:
    """Remove fake registrations after each test.

    Only names this module registered are removed — the shared registry's
    real tools are left untouched, so other test modules keep their
    pre-populated state (including category lists).
    """
    yield
    for name in list(_REGISTERED_NAMES):
        ToolRegistry._tools.pop(name, None)
        for cat in list(ToolRegistry._categories):
            ToolRegistry._categories[cat] = [
                t for t in ToolRegistry._categories[cat] if t.name != name
            ]
            if not ToolRegistry._categories[cat]:
                del ToolRegistry._categories[cat]
    _REGISTERED_NAMES.clear()


class TestToolSource:
    """Unit tests for the _tool_source classifier."""

    @staticmethod
    def test_project_module_is_project() -> None:
        """projects.* functions classify as project source."""
        func = _make_func(
            "projects.uwuchat.server.tools.code_tools.proxy_tools"
        )
        assert _tool_source(func) == "project"

    @staticmethod
    def test_framework_module_is_framework() -> None:
        """airunner_services.* functions classify as framework source."""
        func = _make_func("airunner_services.llm.tools.system_tools")
        assert _tool_source(func) == "framework"

    @staticmethod
    def test_unknown_module_is_extension() -> None:
        """Anything not framework/project is treated as extension."""
        func = _make_func("some_extension.tools")
        assert _tool_source(func) == "extension"

    @staticmethod
    def test_precedence_ordering() -> None:
        """Project outranks extension outranks framework."""
        assert (
            _TOOL_SOURCE_PRECEDENCE["project"]
            > _TOOL_SOURCE_PRECEDENCE["extension"]
        )
        assert (
            _TOOL_SOURCE_PRECEDENCE["extension"]
            > _TOOL_SOURCE_PRECEDENCE["framework"]
        )


class TestRegisterPrecedence:
    """Unit tests for name-collision resolution in ToolRegistry.register."""

    @staticmethod
    def test_framework_does_not_clobber_project() -> None:
        """A project tool already registered must not be replaced by a
        framework reload of the same name."""
        name = "prec_read_file_proxy"
        project_func = _register_fake(
            name,
            "projects.uwuchat.server.tools.code_tools.proxy_tools",
            ToolCategory.CODE,
            requires_agent=True,
            defer_loading=True,
        )
        _register_fake(
            name,
            "airunner_services.llm.tools.system_tools",
            ToolCategory.FILE,
        )

        winner = ToolRegistry.get(name)
        assert winner is not None
        assert winner.func is project_func
        assert winner.category == ToolCategory.CODE

    @staticmethod
    def test_extension_does_not_clobber_project() -> None:
        """An extension re-registration must not replace a project tool."""
        name = "prec_my_tool"
        project_func = _register_fake(
            name,
            "projects.uwuchat.server.tools.some_tools",
            ToolCategory.SYSTEM,
        )
        _register_fake(
            name, "some_extension.tools", ToolCategory.ANALYSIS,
        )

        winner = ToolRegistry.get(name)
        assert winner is not None
        assert winner.func is project_func

    @staticmethod
    def test_project_replaces_framework() -> None:
        """A first-time project registration replaces the framework tool."""
        name = "prec_read_file_second"
        _register_fake(
            name,
            "airunner_services.llm.tools.system_tools",
            ToolCategory.FILE,
        )
        project_func = _register_fake(
            name,
            "projects.uwuchat.server.tools.code_tools.proxy_tools",
            ToolCategory.CODE,
        )

        winner = ToolRegistry.get(name)
        assert winner is not None
        assert winner.func is project_func
        assert winner.category == ToolCategory.CODE

    @staticmethod
    def test_extension_replaces_framework() -> None:
        """An extension registration replaces the framework tool."""
        name = "prec_search_web"
        _register_fake(
            name,
            "airunner_services.tools.web_tools",
            ToolCategory.RESEARCH,
        )
        ext_func = _register_fake(
            name,
            "some_extension.tools",
            ToolCategory.RESEARCH,
        )

        winner = ToolRegistry.get(name)
        assert winner is not None
        assert winner.func is ext_func

    @staticmethod
    def test_equal_precedence_last_wins() -> None:
        """Two registrations from the same source: the later one wins."""
        name = "prec_dup_tool"
        first = _register_fake(
            name,
            "airunner_services.llm.tools.mood_tools",
            ToolCategory.MOOD,
        )
        _register_fake(
            name,
            "airunner_services.llm.tools.social_tools",
            ToolCategory.MOOD,
        )
        second = _register_fake(
            name,
            "airunner_services.llm.tools.mood_tools",
            ToolCategory.MOOD,
        )

        winner = ToolRegistry.get(name)
        assert winner is not None
        assert winner.func is second
        assert winner.func is not first

    @staticmethod
    def test_stale_entry_removed_from_other_categories() -> None:
        """When a name moves categories, the old category list must not
        keep a stale copy of the same name."""
        name = "prec_read_file_cats"
        _register_fake(
            name,
            "airunner_services.llm.tools.system_tools",
            ToolCategory.FILE,
        )
        _register_fake(
            name,
            "projects.uwuchat.server.tools.code_tools.proxy_tools",
            ToolCategory.CODE,
        )

        file_entries = [
            t for t in ToolRegistry.get_by_category(ToolCategory.FILE)
            if t.name == name
        ]
        code_entries = [
            t for t in ToolRegistry.get_by_category(ToolCategory.CODE)
            if t.name == name
        ]
        assert file_entries == []
        assert len(code_entries) == 1

    @staticmethod
    def test_reload_loop_preserves_project_proxy() -> None:
        """The full lazy-reload trigger (a missing-name lookup) must not
        clobber the project proxy with the framework tool."""
        name = "prec_read_file_reload"
        _register_fake(
            name,
            "projects.uwuchat.server.tools.code_tools.proxy_tools",
            ToolCategory.CODE,
        )

        # A missing-name lookup runs _ensure_default_tools_loaded, whose
        # reload loop re-registers framework modules.
        ToolRegistry.get("no_such_tool_xyz")

        winner = ToolRegistry.get(name)
        assert winner is not None
        assert winner.func.__module__ == (
            "projects.uwuchat.server.tools.code_tools.proxy_tools"
        )
        assert winner.category == ToolCategory.CODE
