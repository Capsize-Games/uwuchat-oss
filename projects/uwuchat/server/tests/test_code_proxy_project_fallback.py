"""Unit tests for the code-proxy single-project fallback.

The local Qwen3.5-9B model frequently guesses the registered project
name ("registered-project", "issue-162-project", ...) instead of calling
``list_registered_projects`` first.  When the user has exactly ONE
registered project, any name guess unambiguously refers to it, so the
proxy falls back to it and surfaces the real name in the tool result.
These tests verify the fallback, the name hint, and the multi-project
no-fallback behavior.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import projects.uwuchat.server.headlesscode_client as hc_client
import projects.uwuchat.server.tools.code_tools._path_utils as path_utils
import projects.uwuchat.server.tools.code_tools.proxy_tools as mod

AGENT = SimpleNamespace(
    user=SimpleNamespace(id=7),
    chatbot=SimpleNamespace(id=3),
)
PROJECT_A = SimpleNamespace(
    id=11, name="airunner", repo_path="/srv/airunner",
    workspace_root="/srv/airunner/worktree",
)


def _patch_projects(monkeypatch: pytest.MonkeyPatch, projects: list) -> None:
    """Make HeadlesscodeProject.objects.filter_by filter by name.

    Mirrors the real ORM: an exact-name lookup returns only projects
    with that name; a user-scoped lookup (no name kwarg) returns all.
    """
    def _filter_by(**kw):
        name = kw.get("name")
        if name is None:
            return projects
        return [p for p in projects if p.name == name]

    monkeypatch.setattr(
        path_utils.HeadlesscodeProject.objects, "filter_by", _filter_by,
    )


def _patch_execute_tool(monkeypatch: pytest.MonkeyPatch, result: dict):
    """Return an AsyncMock for headlesscode_client.execute_tool."""
    fake = AsyncMock(return_value=result)
    monkeypatch.setattr(hc_client, "execute_tool", fake)
    return fake


def test_single_project_fallback_resolves_wrong_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A guessed project name resolves when the user has one project."""
    _patch_projects(monkeypatch, [PROJECT_A])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "data"},
    )
    mod.read_file(project_name="issue-162-project", path="a.ts", agent=AGENT)
    assert fake.call_args.args[0] == PROJECT_A.workspace_root


def test_single_project_fallback_surfaces_real_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The result carries a hint naming the real registered project."""
    _patch_projects(monkeypatch, [PROJECT_A])
    _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "data"},
    )
    result = mod.read_file(
        project_name="issue-162-project", path="a.ts", agent=AGENT,
    )
    assert "named 'airunner'" in result


def test_correct_name_no_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Using the real project name produces no substitution hint."""
    _patch_projects(monkeypatch, [PROJECT_A])
    _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "data"},
    )
    result = mod.read_file(project_name="airunner", path="a.ts", agent=AGENT)
    assert "registered project is named" not in result


def test_no_fallback_when_multiple_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With several projects, a wrong name is not silently resolved."""
    other = SimpleNamespace(
        id=12, name="uwuchat", repo_path="/srv/uwuchat",
        workspace_root="/srv/uwuchat/worktree",
    )
    _patch_projects(monkeypatch, [PROJECT_A, other])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "data"},
    )
    result = mod.read_file(
        project_name="issue-162-project", path="a.ts", agent=AGENT,
    )
    assert "isn't a registered project" in result
    fake.assert_not_called()


def test_no_fallback_when_no_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With zero projects, any name is refused with the helpful error."""
    _patch_projects(monkeypatch, [])
    result = mod.read_file(
        project_name="airunner", path="a.ts", agent=AGENT,
    )
    assert "isn't a registered project" in result
