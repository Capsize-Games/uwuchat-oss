"""Unit tests for the code-mode file-edit proxy tools.

Covers argument passing for write_to_file / apply_diff / search_replace /
edit_file through the headlesscode thin proxy. Sibling of
``test_code_proxy_tools.py`` (which covers the command/read/code tools),
split to keep both files under the 250-line limit.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import projects.uwuchat.server.headlesscode_client as hc_client
import projects.uwuchat.server.tools.code_tools._path_utils as path_utils
import projects.uwuchat.server.tools.code_tools.proxy_file_tools as mod

AGENT = SimpleNamespace(
    user=SimpleNamespace(id=7),
    chatbot=SimpleNamespace(id=3),
)
PROJECT = SimpleNamespace(
    id=11, name="acme-web", repo_path="/srv/acme",
    workspace_root="/srv/acme/worktree",
)
WORKSPACE = PROJECT.workspace_root


def _patch_project(monkeypatch: pytest.MonkeyPatch, projects: list) -> None:
    """Make HeadlesscodeProject.objects.filter_by return *projects*."""
    monkeypatch.setattr(
        path_utils.HeadlesscodeProject.objects, "filter_by",
        lambda **kw: projects,
    )


def _patch_execute_tool(monkeypatch: pytest.MonkeyPatch, result: dict):
    """Return an AsyncMock for headlesscode_client.execute_tool."""
    fake = AsyncMock(return_value=result)
    monkeypatch.setattr(hc_client, "execute_tool", fake)
    return fake


def test_write_to_file_forwards_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """write_to_file forwards path + content."""
    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "wrote"},
    )
    result = mod.write_to_file(
        project_name="acme-web", path="notes.txt", content="hi",
        agent=AGENT,
    )
    assert result == "wrote"
    fake.assert_called_once_with(
        WORKSPACE, "write_to_file", {"path": "notes.txt", "content": "hi"},
    )


def test_apply_diff_forwards_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """apply_diff forwards path + diff."""
    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "ok"},
    )
    result = mod.apply_diff(
        project_name="acme-web", path="a.ts", diff="@@ -1 +1 @@", agent=AGENT,
    )
    assert result == "ok"
    fake.assert_called_once_with(
        WORKSPACE, "apply_diff", {"path": "a.ts", "diff": "@@ -1 +1 @@"},
    )


def test_search_replace_forwards_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_replace forwards file_path/old/new."""
    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "ok"},
    )
    result = mod.search_replace(
        project_name="acme-web", file_path="a.ts",
        old_string="foo", new_string="bar", agent=AGENT,
    )
    assert result == "ok"
    fake.assert_called_once_with(
        WORKSPACE, "search_replace",
        {"file_path": "a.ts", "old_string": "foo", "new_string": "bar"},
    )


def test_edit_file_forwards_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """edit_file forwards file_path/old/new + expected_replacements."""
    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "ok"},
    )
    result = mod.edit_file(
        project_name="acme-web", file_path="a.ts",
        old_string="foo", new_string="bar", expected_replacements=2,
        agent=AGENT,
    )
    assert result == "ok"
    fake.assert_called_once_with(
        WORKSPACE, "edit_file",
        {
            "file_path": "a.ts", "old_string": "foo", "new_string": "bar",
            "expected_replacements": 2,
        },
    )


def test_edit_file_omits_expected_replacements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """edit_file without expected_replacements omits it from the payload."""
    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "ok"},
    )
    mod.edit_file(
        project_name="acme-web", file_path="a.ts",
        old_string="foo", new_string="bar", agent=AGENT,
    )
    fake.assert_called_once_with(
        WORKSPACE, "edit_file",
        {"file_path": "a.ts", "old_string": "foo", "new_string": "bar"},
    )
