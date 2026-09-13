"""Unit tests for the code-mode proxy tools (headlesscode thin proxy).

Covers: workspace resolution from the agent context + registered
project, unregistered-project messaging, argument passing to
``headlesscode_client.execute_tool``, result passthrough, and transport
error handling. All dashboard/HTTP and DB interactions are mocked — no
real headlesscode dashboard or database needed.
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
    """Return an AsyncMock for headlesscode_client.execute_tool.

    ``_call_tool`` awaits the client's coroutine via ``_run_async``, so
    the mock must be an AsyncMock (an awaitable), and it must live on
    the client module (``_call_tool`` imports it from there inside the
    function body).
    """
    fake = AsyncMock(return_value=result)
    monkeypatch.setattr(hc_client, "execute_tool", fake)
    return fake


def test_unregistered_project_returns_helpful_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown project names return the registered-project list."""
    _patch_project(monkeypatch, [])
    result = mod.execute_command(
        project_name="nope", command="gh issue list", agent=AGENT,
    )
    assert "isn't a registered project" in result
    assert "none yet" in result


def test_unregistered_lists_other_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Error lists the user's other registered projects."""
    other_a = SimpleNamespace(name="other-web")
    other_b = SimpleNamespace(name="second-web")
    _patch_project(monkeypatch, [])

    def fake_filter(**kw):
        if kw.get("name") == "nope":
            return []
        return [other_a, other_b]

    monkeypatch.setattr(
        path_utils.HeadlesscodeProject.objects, "filter_by", fake_filter,
    )
    result = mod.execute_command(
        project_name="nope", command="gh issue list", agent=AGENT,
    )
    assert "other-web" in result


def test_execute_command_passes_workspace_and_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """execute_command resolves the worktree and forwards args verbatim."""
    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "done\n"},
    )
    result = mod.execute_command(
        project_name="acme-web",
        command="gh issue list",
        cwd="sub",
        timeout=30,
        agent=AGENT,
    )
    assert result == "done\n"
    fake.assert_called_once_with(
        WORKSPACE, "execute_command",
        {"command": "gh issue list", "cwd": "sub", "timeout": 30},
    )


def test_optional_args_omitted_when_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional args absent from the forwarded payload when not provided."""
    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "ok"},
    )
    mod.execute_command(project_name="acme-web", command="ls", agent=AGENT)
    fake.assert_called_once_with(WORKSPACE, "execute_command", {"command": "ls"})


def test_read_file_forwards_offset_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """read_file forwards path/offset/limit."""
    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "content"},
    )
    result = mod.read_file(
        project_name="acme-web", path="src/a.ts", offset=2, limit=5,
        agent=AGENT,
    )
    assert result == "content"
    fake.assert_called_once_with(
        WORKSPACE, "read_file", {"path": "src/a.ts", "offset": 2, "limit": 5},
    )


def test_list_files_forwards_recursive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """list_files forwards path + recursive."""
    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "a\nb"},
    )
    result = mod.list_files(
        project_name="acme-web", path="src", recursive=True, agent=AGENT,
    )
    assert result == "a\nb"
    fake.assert_called_once_with(
        WORKSPACE, "list_files", {"path": "src", "recursive": True},
    )


def test_codebase_search_and_run_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """codebase_search + run_tests forward their args."""
    _patch_project(monkeypatch, [PROJECT])

    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "hits"},
    )
    result = mod.codebase_search(
        project_name="acme-web", query="auth", agent=AGENT,
    )
    assert result == "hits"
    fake.assert_called_once_with(
        WORKSPACE, "codebase_search", {"query": "auth"},
    )

    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "pass"},
    )
    result = mod.run_tests(
        project_name="acme-web", test_command="npm test", agent=AGENT,
    )
    assert result == "pass"
    fake.assert_called_once_with(
        WORKSPACE, "run_tests", {"test_command": "npm test"},
    )


def test_run_tests_omits_empty_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_tests without a command forwards an empty args dict."""
    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "pass"},
    )
    mod.run_tests(project_name="acme-web", agent=AGENT)
    fake.assert_called_once_with(WORKSPACE, "run_tests", {})


def test_error_result_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Harness-side errors (isError=True) propagate content as-is."""
    _patch_project(monkeypatch, [PROJECT])
    _patch_execute_tool(
        monkeypatch,
        {
            "ok": False,
            "isError": True,
            "content": "[Error] Unknown tool: nope",
        },
    )
    result = mod.read_file(project_name="acme-web", path="a.ts", agent=AGENT)
    assert "[Error] Unknown tool: nope" in result


def test_transport_error_returns_friendly_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dashboard transport failure degrades to a friendly error."""
    _patch_project(monkeypatch, [PROJECT])

    async def boom(*args, **kwargs):
        raise ConnectionError("dashboard unreachable")

    monkeypatch.setattr(hc_client, "execute_tool", boom)
    result = mod.execute_command(
        project_name="acme-web", command="ls", agent=AGENT,
    )
    assert "Tool error" in result
    assert "dashboard unreachable" in result


def test_missing_agent_returns_unregistered_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No agent context degrades to the unregistered-project error."""
    _patch_project(monkeypatch, [])
    result = mod.execute_command(
        project_name="acme-web", command="ls", agent=None,
    )
    assert "isn't a registered project" in result
