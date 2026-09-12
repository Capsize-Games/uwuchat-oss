"""Unit tests for code-proxy absolute-path normalization.

The local code-mode model frequently passes absolute paths to the file
tools — the worktree root (``/home/.../headlesscode-worktrees/...``) or
the primary checkout (``/home/<user>/Projects/airunner/...``) — which the
harness's path-safety correctly refuses.  The proxy normalizes paths
that live inside the workspace (or the repo it tracks) back to
worktree-relative before dispatch.  These tests verify the rewrite and
that genuinely-outside paths are left for the harness to refuse.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import projects.uwuchat.server.headlesscode_client as hc_client
import projects.uwuchat.server.tools.code_tools._edit_expansion as edit_exp
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
    """Return an AsyncMock for headlesscode_client.execute_tool."""
    fake = AsyncMock(return_value=result)
    monkeypatch.setattr(hc_client, "execute_tool", fake)
    return fake


def test_absolute_worktree_path_rewritten_to_relative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absolute path under the worktree is rewritten to relative."""
    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "data"},
    )
    mod.read_file(project_name="acme-web", path=f"{WORKSPACE}/src/app.ts",
                  agent=AGENT)
    assert fake.call_args.args[2] == {"path": "src/app.ts"}


def test_absolute_repo_path_rewritten_to_relative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absolute path under the primary checkout maps to the same
    relative path (the worktree mirrors the repo layout)."""
    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "data"},
    )
    mod.read_file(project_name="acme-web", path=f"{PROJECT.repo_path}/src/app.ts",
                  agent=AGENT)
    assert fake.call_args.args[2] == {"path": "src/app.ts"}


def test_relative_path_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """A relative path is passed through untouched."""
    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "data"},
    )
    mod.read_file(project_name="acme-web", path="src/app.ts", agent=AGENT)
    assert fake.call_args.args[2] == {"path": "src/app.ts"}


def test_outside_path_left_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """A path outside both workspace and repo stays absolute — the
    harness's containment still refuses it."""
    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "data"},
    )
    mod.read_file(project_name="acme-web", path="/etc/passwd", agent=AGENT)
    assert fake.call_args.args[2] == {"path": "/etc/passwd"}


def test_file_path_key_normalized_for_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """edit_file's file_path arg is normalized like the path arg."""
    from projects.uwuchat.server.tools.code_tools.proxy_file_tools import (
        edit_file,
    )

    _patch_project(monkeypatch, [PROJECT])
    fake = _patch_execute_tool(
        monkeypatch, {"ok": True, "isError": False, "content": "done"},
    )
    edit_file(
        project_name="acme-web",
        file_path=f"{WORKSPACE}/src/app.ts",
        old_string="a",
        new_string="b",
        agent=AGENT,
    )
    assert fake.call_args.args[2] == {
        "file_path": "src/app.ts",
        "old_string": "a",
        "new_string": "b",
    }


def test_hallucinated_absolute_path_suffix_stripped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bogus absolute path (e.g. /usr/local/plans/...) has its system
    mount prefix stripped, yielding the repo-relative path."""
    bogus = "/usr/local/plans/parallel-tasks/w16-continue2.md"
    result = path_utils._relative_to_workspace(
        bogus, "/srv/acme/worktree", "/srv/acme",
    )
    assert result == "plans/parallel-tasks/w16-continue2.md"


def test_outside_absolute_path_without_repo_dir_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A genuine outside path (e.g. /etc/passwd) is NOT stripped — the
    harness still refuses it, preserving containment."""
    result = path_utils._relative_to_workspace(
        "/etc/passwd", "/srv/acme/worktree", "/srv/acme",
    )
    assert result == "/etc/passwd"


def test_relative_path_still_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Relative paths are untouched by the bogus-prefix stripping."""
    result = path_utils._relative_to_workspace(
        "src/app.ts", "/srv/acme/worktree", "/srv/acme",
    )
    assert result == "src/app.ts"


def test_credential_map_strings_flattened() -> None:
    """JSON-stringified credential maps are flattened to the values."""
    args = {
        "old_string": '{"email": "user@example.com", '
                      '"password": "example-lan-password"}',
        "new_string": '{"email": "<staging-user>@example.com", '
                      '"password": "<staging-password>"}',
    }
    flattened = edit_exp._coerce_string_args(args)
    assert "user@example.com" in flattened["old_string"]
    assert "example-lan-password" in flattened["old_string"]


def test_credential_map_expands_to_pairs() -> None:
    """JSON credential maps expand into per-key replacement pairs."""
    pairs = edit_exp._expand_credential_replacements(
        '{"email": "user@example.com", "password": "example-lan-password"}',
        '{"email": "<staging-user>@example.com", '
        '"password": "<staging-password>"}',
    )
    assert pairs == [
        ("user@example.com", "<staging-user>@example.com"),
        ("example-lan-password", "<staging-password>"),
    ]


def test_plain_strings_not_expanded() -> None:
    """Plain string args produce a single literal pair."""
    pairs = edit_exp._expand_credential_replacements("foo", "bar")
    assert pairs == [("foo", "bar")]


def test_found_occurrence_count_parsed() -> None:
    """The harness mismatch error's found-count is parsed."""
    err = (
        "edit_file: occurrence count mismatch in file 'x.md'\n\n"
        "<error_details>\n"
        "Expected 1 occurrence(s) but found 3 exact match(es)."
    )
    assert edit_exp._found_occurrence_count(err) == 3


def test_found_occurrence_count_none_for_success() -> None:
    """A success message yields no count (no retry needed)."""
    assert edit_exp._found_occurrence_count(
        "File updated: x.md (3 replacements)"
    ) is None
