"""Unit tests for the code-mode command/arg edge cases in proxy_tools.

Covers the branches the main proxy test file does not: the absolute-cwd
drop for execute_command, the timeout arg passthrough, and the arg
omission paths for read_file/list_files/run_tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import projects.uwuchat.server.headlesscode_client as hc_client
import projects.uwuchat.server.tools.code_tools._path_utils as path_utils
import projects.uwuchat.server.tools.code_tools.proxy_tools as mod

AGENT = SimpleNamespace(
    user=SimpleNamespace(id=7),
    chatbot=SimpleNamespace(id=3),
)
PROJECT = SimpleNamespace(
    id=11, name="acme-web", repo_path="/srv/acme",
    workspace_root="/srv/acme/worktree",
)


def _patch_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        path_utils.HeadlesscodeProject.objects, "filter_by",
        lambda **kw: [PROJECT],
    )


def _patch_execute_tool(monkeypatch: pytest.MonkeyPatch, result: dict):
    fake = AsyncMock(return_value=result)
    monkeypatch.setattr(hc_client, "execute_tool", fake)
    return fake


def test_execute_command_drops_absolute_cwd(monkeypatch) -> None:
    """An absolute cwd is dropped so the harness path-safety can't refuse."""
    _patch_project(monkeypatch)
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "ok"},
    )
    mod.execute_command(
        project_name="acme-web",
        command="ls",
        cwd="/srv/acme",  # absolute → dropped
        agent=AGENT,
    )
    fake.assert_called_once_with(
        PROJECT.workspace_root, "execute_command", {"command": "ls"},
    )


def test_execute_command_keeps_relative_cwd(monkeypatch) -> None:
    """A relative cwd is forwarded."""
    _patch_project(monkeypatch)
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "ok"},
    )
    mod.execute_command(
        project_name="acme-web", command="ls", cwd="src", agent=AGENT,
    )
    fake.assert_called_once_with(
        PROJECT.workspace_root, "execute_command",
        {"command": "ls", "cwd": "src"},
    )


def test_execute_command_with_timeout(monkeypatch) -> None:
    """A numeric timeout is forwarded."""
    _patch_project(monkeypatch)
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "ok"},
    )
    mod.execute_command(
        project_name="acme-web", command="sleep 5", timeout=30, agent=AGENT,
    )
    fake.assert_called_once_with(
        PROJECT.workspace_root, "execute_command",
        {"command": "sleep 5", "timeout": 30},
    )


def test_read_file_omits_none_offset_limit(monkeypatch) -> None:
    """read_file without offset/limit omits them from the payload."""
    _patch_project(monkeypatch)
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "x"},
    )
    mod.read_file(project_name="acme-web", path="a.ts", agent=AGENT)
    fake.assert_called_once_with(
        PROJECT.workspace_root, "read_file", {"path": "a.ts"},
    )


def test_list_files_defaults(monkeypatch) -> None:
    """list_files uses '.' and recursive=False by default."""
    _patch_project(monkeypatch)
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "x"},
    )
    mod.list_files(project_name="acme-web", agent=AGENT)
    fake.assert_called_once_with(
        PROJECT.workspace_root, "list_files",
        {"path": ".", "recursive": False},
    )


def test_run_tests_with_command(monkeypatch) -> None:
    """run_tests with an explicit command forwards it."""
    _patch_project(monkeypatch)
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "pass"},
    )
    mod.run_tests(
        project_name="acme-web", test_command="npm test", agent=AGENT,
    )
    fake.assert_called_once_with(
        PROJECT.workspace_root, "run_tests", {"test_command": "npm test"},
    )


def test_call_tool_delegate_invoked(monkeypatch) -> None:
    """Each tool delegates through call_tool with its tool name.

    call_tool is imported into proxy_tools' module namespace at import
    time, so the patch must target the proxy_tools namespace.
    """
    _patch_project(monkeypatch)
    with patch(
        "projects.uwuchat.server.tools.code_tools.proxy_tools.call_tool"
    ) as ct:
        ct.return_value = "ok"
        mod.codebase_search(
            project_name="acme-web", query="auth", agent=AGENT,
        )
    ct.assert_called_once_with(
        AGENT, "acme-web", "codebase_search", {"query": "auth"},
    )
