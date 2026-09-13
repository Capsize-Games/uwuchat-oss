"""Project-name discovery tool for code mode.

Lets the model learn the user's exact registered project names instead
of guessing them ("airunner" → "air unner"). Queries the same
user-scoped ``HeadlesscodeProject`` table the proxy helpers use, so it
can never reveal projects belonging to another user.  The GitHub
owner/name for each project comes from the headlesscode dashboard
(``GET /api/projects`` → ``gitOwnerName``), which is the only component
that can read the worktree's git remote.
"""

from __future__ import annotations

from typing import Any

from airunner_services.llm.core.tool_registry import ToolCategory, tool

from projects.uwuchat.server.models.headlesscode_project import (
    HeadlesscodeProject,
)

_NO_PROJECTS_MSG = (
    "No registered projects yet — add one in settings before using "
    "the code tools."
)


def _dashboard_owner_by_path() -> dict[str, str]:
    """Return ``{filesystem_path: owner/name}`` from the dashboard.

    The dashboard exposes each registered project's git remote owner
    (``gitOwnerName``) via ``GET /api/projects``.  Falls back to an
    empty dict when the dashboard is unreachable — the caller then
    shows ``owner/name=<unknown>`` rather than failing the whole list.
    """
    try:
        from projects.uwuchat.server import headlesscode_client
        from projects.uwuchat.server.tools.code_tools._proxy_helpers import (
            run_async,
        )

        entries = run_async(headlesscode_client.list_projects())
    except Exception:
        return {}
    result: dict[str, str] = {}
    for entry in entries or []:
        project_path = entry.get("path")
        owner = entry.get("gitOwnerName")
        if project_path and owner:
            result[project_path] = owner
    return result


@tool(
    name="list_registered_projects",
    category=ToolCategory.CODE,
    description=(
        "List the user's registered projects with their GitHub "
        "owner/name (owner/name) and local path. Use the owner/name as "
        "the --repo value for gh (e.g. `gh issue list --repo "
        "<your-org>/airunnerweb`). Call this BEFORE guessing a "
        "project name or repo — always use the exact name and "
        "owner/name it returns."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=False,
    keywords=["projects", "registered", "registry", "list projects"],
    input_examples=[{}],
)
def list_registered_projects(agent: Any = None) -> str:
    """Return the user's registered projects, one per line."""
    user = getattr(agent, "user", None) if agent else None
    user_id = getattr(user, "id", None) if user else None
    if not user_id:
        return (
            "Could not identify the current user — cannot list "
            "registered projects."
        )
    projects = HeadlesscodeProject.objects.filter_by(
        user_id=user_id, deleted=False,
    )
    if not projects:
        return _NO_PROJECTS_MSG
    owners = _dashboard_owner_by_path()
    lines = []
    for p in projects:
        owner = owners.get(p.repo_path)
        owner_part = f"owner/name={owner}" if owner else "owner/name=<unknown>"
        lines.append(f"{p.name} ({p.repo_path}) {owner_part}")
    return "\n".join(lines)


__all__ = ["list_registered_projects"]
