"""Unit tests for the ``list_registered_projects`` code-mode tool.

Verifies the user-scoped registry lookup: registered projects are
returned one per line with their GitHub owner/name (from the headlesscode
dashboard), an empty registry returns the settings guidance, and a
missing agent/user degrades gracefully.  All DB interactions and the
dashboard call are mocked — no real database or dashboard.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from projects.uwuchat.server.tools.code_tools import registry_tool as mod

AGENT = SimpleNamespace(
    user=SimpleNamespace(id=7),
    chatbot=SimpleNamespace(id=3),
)


def _project(
    name: str, repo_path: str, workspace_root: str = "/wt/airunner",
) -> SimpleNamespace:
    """Return a fake HeadlesscodeProject row."""
    return SimpleNamespace(
        name=name, repo_path=repo_path, workspace_root=workspace_root,
    )


def _patch_projects(monkeypatch: pytest.MonkeyPatch, projects: list) -> None:
    """Make HeadlesscodeProject.objects.filter_by return *projects*."""
    monkeypatch.setattr(
        mod.HeadlesscodeProject.objects, "filter_by",
        lambda **kw: projects,
    )


def _patch_owners(monkeypatch: pytest.MonkeyPatch, owners: dict) -> None:
    """Stub the dashboard owner lookup."""
    monkeypatch.setattr(mod, "_dashboard_owner_by_path", lambda: owners)


def test_lists_registered_projects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two registered projects are both returned, one per line."""
    _patch_projects(
        monkeypatch,
        [_project("airunner", "/srv/airunner"),
         _project("fastsearch", "/srv/fastsearch")],
    )
    _patch_owners(
        monkeypatch,
        {"/srv/airunner": "<your-org>/airunnerweb"},
    )
    result = mod.list_registered_projects(agent=AGENT)
    assert "airunner" in result
    assert "fastsearch" in result
    assert "/srv/airunner" in result
    assert "owner/name=<your-org>/airunnerweb" in result
    assert len(result.splitlines()) == 2


def test_no_registered_projects_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty registry returns the add-one-in-settings guidance."""
    _patch_projects(monkeypatch, [])
    result = mod.list_registered_projects(agent=AGENT)
    assert "No registered projects yet" in result


def test_missing_agent_returns_graceful_error() -> None:
    """agent=None returns a graceful error string, no crash."""
    result = mod.list_registered_projects(agent=None)
    assert "Could not identify" in result


def test_missing_user_id_returns_graceful_error() -> None:
    """An agent without a user id returns a graceful error, no crash."""
    result = mod.list_registered_projects(
        agent=SimpleNamespace(user=None),
    )
    assert "Could not identify" in result


def test_unknown_owner_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the dashboard has no owner for a path, surface <unknown>."""
    _patch_projects(
        monkeypatch,
        [_project("airunner", "/srv/airunner")],
    )
    _patch_owners(monkeypatch, {})
    result = mod.list_registered_projects(agent=AGENT)
    assert "owner/name=<unknown>" in result


def test_dashboard_owner_by_path_parses_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_dashboard_owner_by_path maps dashboard entries to owners."""
    async def fake_list_projects() -> list[dict]:
        return [
            {
                "key": "airunner",
                "path": "/srv/airunner",
                "registered": True,
                "exists": True,
                "gitOwnerName": "<your-org>/airunnerweb",
            },
            {
                "key": "other",
                "path": "/srv/other",
                "registered": True,
                "exists": True,
                # No owner → skipped.
            },
        ]

    import projects.uwuchat.server.headlesscode_client as hc

    monkeypatch.setattr(hc, "list_projects", fake_list_projects)
    owners = mod._dashboard_owner_by_path()
    assert owners == {"/srv/airunner": "<your-org>/airunnerweb"}


def test_dashboard_owner_by_path_graceful_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreachable dashboard yields an empty owner map, no crash."""
    import projects.uwuchat.server.headlesscode_client as hc

    async def boom() -> list[dict]:
        raise RuntimeError("dashboard down")

    monkeypatch.setattr(hc, "list_projects", boom)
    assert mod._dashboard_owner_by_path() == {}
