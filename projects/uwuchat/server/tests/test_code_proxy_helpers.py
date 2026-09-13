"""Unit tests for the code-mode proxy helper functions.

Covers ``unregistered_message``, the host-exec routing helpers
(``_host_exec_result`` / ``_matches_policy`` / ``_dispatch_host``),
``_resolve_workspace``, and ``call_tool`` (the execute_command
result path that returns the harness output as the tool result —
the exact surface that was missing from the GUI stream).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import projects.uwuchat.server.headlesscode_client as hc_client
import projects.uwuchat.server.tools.code_tools._path_utils as path_utils
import projects.uwuchat.server.tools.code_tools._proxy_helpers as helpers

AGENT = SimpleNamespace(
    user=SimpleNamespace(id=7),
    chatbot=SimpleNamespace(id=3),
)
PROJECT = SimpleNamespace(
    id=11, name="acme-web", repo_path="/srv/acme",
    workspace_root="/srv/acme/worktree",
)


def _usable_workspace_fixture(tmp_path) -> str:
    """Create a real (git-like) workspace dir and return its path."""
    ws = tmp_path / "worktree"
    ws.mkdir()
    (ws / ".git").mkdir()
    (ws / "src").mkdir()
    return str(ws)


def _patch_projects(monkeypatch: pytest.MonkeyPatch, projects: list) -> None:
    """Mirror the real ORM: name lookups filter, user-only returns all."""

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


# ---------------------------------------------------------------------------
# unregistered_message
# ---------------------------------------------------------------------------


def test_unregistered_message_lists_projects(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_projects(monkeypatch, [PROJECT, SimpleNamespace(name="other")])
    msg = helpers.unregistered_message("nope", 7)
    assert "isn't a registered project" in msg
    assert "acme-web" in msg
    assert "other" in msg


def test_unregistered_message_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_projects(monkeypatch, [])
    msg = helpers.unregistered_message("nope", 7)
    assert "none yet" in msg


# ---------------------------------------------------------------------------
# _host_exec_result
# ---------------------------------------------------------------------------


def test_host_exec_container_safe() -> None:
    result = helpers._host_exec_result("ls", AGENT.user)
    assert "container-safe" in result


def test_host_exec_disabled_by_policy() -> None:
    policy = SimpleNamespace(enabled=False)
    with patch(
        "projects.uwuchat.server.host_exec_policy.HostExecPolicy.from_user_data",
        return_value=policy,
    ):
        result = helpers._host_exec_result("gh issue close 5", AGENT.user)
    assert "disabled" in result


def test_host_exec_hard_blacklist() -> None:
    policy = SimpleNamespace(enabled=True)
    with patch(
        "projects.uwuchat.server.host_exec_policy.HostExecPolicy.from_user_data",
        return_value=policy,
    ), patch(
        "projects.uwuchat.server.host_exec_policy.needs_host",
        return_value=True,
    ):
        result = helpers._host_exec_result("sudo rm -rf /", AGENT.user)
    assert "blocked" in result


def test_host_exec_allow_all_dispatches() -> None:
    policy = SimpleNamespace(
        enabled=True, enable_all=True, whitelist=[], allow_always=[],
    )
    with patch(
        "projects.uwuchat.server.host_exec_policy.HostExecPolicy.from_user_data",
        return_value=policy,
    ), patch(
        "projects.uwuchat.server.host_exec_policy.needs_host",
        return_value=True,
    ), patch.object(helpers, "_dispatch_host", return_value="out") as dispatch:
        result = helpers._host_exec_result("gh issue list", AGENT.user)
    assert result == "out"
    dispatch.assert_called_once()


def test_host_exec_matches_policy() -> None:
    policy = SimpleNamespace(
        enabled=True, enable_all=False, whitelist=["gh issue"], allow_always=[],
    )
    with patch(
        "projects.uwuchat.server.host_exec_policy.HostExecPolicy.from_user_data",
        return_value=policy,
    ), patch(
        "projects.uwuchat.server.host_exec_policy.needs_host",
        return_value=True,
    ), patch.object(helpers, "_dispatch_host", return_value="out"):
        result = helpers._host_exec_result("gh issue list", AGENT.user)
    assert result == "out"


def test_host_exec_needs_consent_marker() -> None:
    policy = SimpleNamespace(
        enabled=True, enable_all=False, whitelist=[], allow_always=[],
    )
    with patch(
        "projects.uwuchat.server.host_exec_policy.HostExecPolicy.from_user_data",
        return_value=policy,
    ), patch(
        "projects.uwuchat.server.host_exec_policy.needs_host",
        return_value=True,
    ):
        result = helpers._host_exec_result("gh issue list", AGENT.user)
    assert "HOST_EXEC_CONSENT::" in result
    assert "needs_consent" in result


# ---------------------------------------------------------------------------
# _matches_policy
# ---------------------------------------------------------------------------


def test_matches_policy_substring() -> None:
    policy = SimpleNamespace(
        whitelist=["gh issue"], allow_always=["gh pr"],
    )
    assert helpers._matches_policy("gh issue list", policy) is True
    assert helpers._matches_policy("gh pr create", policy) is True


def test_matches_policy_false() -> None:
    policy = SimpleNamespace(whitelist=["gh issue"], allow_always=[])
    assert helpers._matches_policy("rm -rf", policy) is False


def test_matches_policy_skips_empty_patterns() -> None:
    policy = SimpleNamespace(whitelist=["", None], allow_always=[""])
    assert helpers._matches_policy("anything", policy) is False


# ---------------------------------------------------------------------------
# _dispatch_host
# ---------------------------------------------------------------------------


def test_dispatch_host_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "projects.uwuchat.server.host_exec_client.available", lambda: False
    )
    result = helpers._dispatch_host("gh issue list", lambda c: {})
    assert "not running" in result


def test_dispatch_host_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "projects.uwuchat.server.host_exec_client.available", lambda: True
    )
    result = helpers._dispatch_host(
        "gh issue list", lambda c: {"status": "ok", "output": "issue 5"}
    )
    assert result == "issue 5"


def test_dispatch_host_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "projects.uwuchat.server.host_exec_client.available", lambda: True
    )
    result = helpers._dispatch_host(
        "gh issue list", lambda c: {"status": "denied", "output": "nope"}
    )
    assert "denied: nope" in result


def test_dispatch_host_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "projects.uwuchat.server.host_exec_client.available", lambda: True
    )
    result = helpers._dispatch_host(
        "gh issue list", lambda c: {"status": "error", "output": "boom"}
    )
    assert "error: boom" in result


# ---------------------------------------------------------------------------
# _resolve_workspace
# ---------------------------------------------------------------------------


def test_resolve_workspace_unregistered(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_projects(monkeypatch, [])
    resolved = helpers._resolve_workspace(7, "nope")
    assert isinstance(resolved, str)
    assert "isn't a registered project" in resolved


def test_resolve_workspace_with_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    ws = _usable_workspace_fixture(tmp_path)
    project = SimpleNamespace(
        id=11, name="acme-web", repo_path="/srv/acme",
        workspace_root=ws,
    )
    _patch_projects(monkeypatch, [project])
    real_name, workspace, hint, repo_path = helpers._resolve_workspace(
        7, "wrong-name"
    )
    assert real_name == "acme-web"
    assert workspace == ws
    assert "named 'acme-web'" in hint
    assert repo_path == "/srv/acme"


def test_resolve_workspace_no_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    ws = _usable_workspace_fixture(tmp_path)
    project = SimpleNamespace(
        id=11, name="acme-web", repo_path="/srv/acme",
        workspace_root=ws,
    )
    _patch_projects(monkeypatch, [project])
    real_name, _workspace, hint, repo_path = helpers._resolve_workspace(
        7, "acme-web"
    )
    assert real_name == "acme-web"
    assert hint == ""
    assert repo_path == "/srv/acme"


def test_resolve_workspace_no_repo_path(monkeypatch: pytest.MonkeyPatch) -> None:
    bare = SimpleNamespace(
        id=1, name="bare", repo_path=None, workspace_root="/srv/bare/wt"
    )
    _patch_projects(monkeypatch, [bare])
    real_name, _workspace, _hint, repo_path = helpers._resolve_workspace(
        7, "bare"
    )
    assert real_name == "bare"
    assert repo_path is None


def test_resolve_workspace_stale_empty_falls_back_to_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """An empty/stale worktree (only .headlesscode/) falls back to the
    primary checkout so tool calls work against real code."""
    stale = tmp_path / "stale-worktree"
    stale.mkdir()
    (stale / ".headlesscode").mkdir()
    project = SimpleNamespace(
        id=11, name="acme-web", repo_path="/srv/acme",
        workspace_root=str(stale),
    )
    _patch_projects(monkeypatch, [project])
    real_name, workspace, hint, repo_path = helpers._resolve_workspace(
        7, "acme-web"
    )
    assert real_name == "acme-web"
    assert workspace == "/srv/acme"  # fell back to the primary checkout
    assert "empty/stale" in hint
    assert repo_path == "/srv/acme"


def test_resolve_workspace_missing_dir_left_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """A workspace_root that doesn't exist is NOT rewritten.

    A not-yet-created worktree dir (or a test fake path) passes through
    unchanged — only an existing-but-empty dir is treated as stale.
    """
    missing = str(tmp_path / "gone-worktree")
    project = SimpleNamespace(
        id=11, name="acme-web", repo_path="/srv/acme",
        workspace_root=missing,
    )
    _patch_projects(monkeypatch, [project])
    real_name, workspace, _hint, repo_path = helpers._resolve_workspace(
        7, "acme-web"
    )
    assert real_name == "acme-web"
    assert workspace == missing  # unchanged
    assert repo_path == "/srv/acme"


# ---------------------------------------------------------------------------
# call_tool
# ---------------------------------------------------------------------------


def test_call_tool_no_agent() -> None:
    result = helpers.call_tool(None, "acme-web", "execute_command", {"command": "ls"})
    assert "isn't a registered project" in result


def test_call_tool_unregistered_project(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_projects(monkeypatch, [])
    result = helpers.call_tool(
        AGENT, "acme-web", "execute_command", {"command": "ls"}
    )
    assert "isn't a registered project" in result


def test_call_tool_forwards_and_returns_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    ws = _usable_workspace_fixture(tmp_path)
    project = SimpleNamespace(
        id=11, name="acme-web", repo_path="/srv/acme",
        workspace_root=ws,
    )
    _patch_projects(monkeypatch, [project])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "out"},
    )
    result = helpers.call_tool(
        AGENT, "acme-web", "execute_command", {"command": "ls"}
    )
    assert result == "out"
    fake.assert_called_once_with(ws, "execute_command", {"command": "ls"})


def test_call_tool_result_with_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_projects(monkeypatch, [PROJECT])
    _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "out"},
    )
    result = helpers.call_tool(
        AGENT, "guessed-name", "execute_command", {"command": "ls"}
    )
    assert "named 'acme-web'" in result
    assert "out" in result


def test_call_tool_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_projects(monkeypatch, [PROJECT])

    async def boom(*args, **kwargs):
        raise ConnectionError("down")

    monkeypatch.setattr(hc_client, "execute_tool", boom)
    result = helpers.call_tool(
        AGENT, "acme-web", "execute_command", {"command": "ls"}
    )
    assert "Tool error" in result


def test_call_tool_host_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    """execute_command with a host-needing command routes to host."""
    _patch_projects(monkeypatch, [PROJECT])
    with patch(
        "projects.uwuchat.server.host_exec_policy.needs_host",
        return_value=True,
    ), patch.object(helpers, "_host_exec_result", return_value="host-out"):
        result = helpers.call_tool(
            AGENT, "acme-web", "execute_command", {"command": "gh issue list"}
        )
    assert result == "host-out"


def test_call_tool_edit_expansion(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """edit_file with an expanded credential edit short-circuits.

    _expand_credential_edit is imported at module top of _proxy_helpers,
    so the patch must target the _proxy_helpers namespace.
    """
    ws = _usable_workspace_fixture(tmp_path)
    project = SimpleNamespace(
        id=11, name="acme-web", repo_path="/srv/acme",
        workspace_root=ws,
    )
    _patch_projects(monkeypatch, [project])
    with patch(
        "projects.uwuchat.server.tools.code_tools._proxy_helpers._expand_credential_edit",
        return_value="expanded",
    ):
        result = helpers.call_tool(
            AGENT, "acme-web", "edit_file",
            {"file_path": "a.ts", "old_string": "x", "new_string": "y"},
        )
    assert result == "expanded"


def test_call_tool_path_normalization(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """Path args are normalized before dispatch."""
    ws = _usable_workspace_fixture(tmp_path)
    project = SimpleNamespace(
        id=11, name="acme-web", repo_path="/srv/acme",
        workspace_root=ws,
    )
    _patch_projects(monkeypatch, [project])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "ok"},
    )
    with patch.object(
        helpers, "_normalize_tool_path_args",
        return_value={"path": "rel/a.ts"},
    ):
        helpers.call_tool(
            AGENT, "acme-web", "read_file", {"path": "/abs/a.ts"}
        )
    fake.assert_called_once_with(ws, "read_file", {"path": "rel/a.ts"})
