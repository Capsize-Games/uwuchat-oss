"""Path/workspace resolution helpers for the code-mode proxy tools.

Shared between ``_proxy_helpers.py`` (thin harness proxy) and
``_edit_expansion.py`` (credential-map edit expansion).  Keeping them
here avoids a circular import between those two modules.
"""

from __future__ import annotations

import asyncio

from projects.uwuchat.server.models.headlesscode_project import (
    HeadlesscodeProject,
)

# Shared parameter description: which registered project a tool targets.
PROJECT_PARAM = "Exact registered project name to work on."

# System directory names that never begin a repo-relative path.  When
# the model fabricates an absolute path (e.g. ``/usr/local/plans/...``)
# these leading components are the bogus mount prefix to strip.
_SYSTEM_PATH_COMPONENTS = frozenset({
    "bin", "boot", "dev", "etc", "home", "lib", "lib64", "local",
    "media", "mnt", "opt", "proc", "root", "run", "sbin", "srv",
    "sys", "tmp", "usr", "var", "workspace", "workspaces", "app",
    "data", "data1", "code",
})

# Plausible repo top-level directories.  A stripped path must begin
# with one of these — otherwise the "hallucinated prefix" theory is
# wrong (e.g. ``/etc/passwd`` is a genuine outside path and must stay
# absolute for the harness to refuse).
_REPO_TOP_DIRS = frozenset({
    "client", "deploy", "docker", "docs", "extensions", "images",
    "package", "packages", "plans", "projects", "qa", "scripts",
    "server", "src", "tests", "wiki",
})


def run_async(coro):
    """Run an async coroutine in a sync context (tool functions are sync)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _registered_projects(user_id: int) -> list:
    """Return the user's non-deleted registered projects."""
    return HeadlesscodeProject.objects.filter_by(user_id=user_id)


def _single_project_fallback(user_id: int) -> list | None:
    """Return [(name, workspace)] when the user has exactly ONE project.

    The local Qwen3.5-9B model frequently guesses the project name
    ("registered-project", "issue-162-project", ...) instead of calling
    ``list_registered_projects`` first.  When the user has a single
    registered project, any name guess unambiguously refers to it — so
    fall back to it (mirroring how the GUI works on the open workspace)
    and surface the real name in the tool result so the model learns it.
    Returns None when the user has zero or multiple projects.
    """
    projects = _registered_projects(user_id)
    if len(projects) != 1:
        return None
    return [(projects[0].name, projects[0].workspace_root)]


def _strip_bogus_absolute_prefix(
    path: str,
    workspace: str,
) -> str:
    """Return the repo-relative suffix of a hallucinated absolute path.

    The local model occasionally fabricates container-style absolute
    paths (``/usr/local/plans/parallel-tasks/w16-continue2.md``) that
    the harness's path-safety refuses.  The server container cannot
    stat the worktree (it is mounted only in the harness), so strip
    the bogus leading mount prefix textually: drop leading system
    components, then keep the result only if it begins with a known
    repo top-level directory.  A path like ``/etc/passwd`` fails that
    test and stays unchanged (the harness still refuses it).
    """
    import os as _os

    parts = [p for p in path.split(_os.sep) if p]
    kept: list[str] = []
    for part in parts:
        if not kept and part in _SYSTEM_PATH_COMPONENTS:
            continue
        kept.append(part)
    candidate = "/".join(kept)
    if not candidate:
        return path
    first = candidate.split("/")[0]
    if first not in _REPO_TOP_DIRS:
        return path
    return candidate


def _relative_to_workspace(
    path: str,
    workspace: str,
    repo_path: str | None,
) -> str:
    """Return *path* as a workspace-relative path, or unchanged.

    The model occasionally invents absolute paths — the worktree root
    (``/home/<user>/.local/share/headlesscode-worktrees/airunner-.../plans/
    ...``), the primary checkout (``/home/<user>/Projects/airunner/plans/
    ...``), or a bogus container path (``/usr/local/plans/...``) —
    which the harness's path-safety correctly refuses.  When the
    resolved path lives INSIDE the workspace (or inside the repo the
    workspace tracks), rewrite it to the equivalent relative path so
    the call succeeds.  A hallucinated absolute path OUTSIDE both has
    its bogus mount prefix stripped (see
    :func:`_strip_bogus_absolute_prefix`).  Containment is preserved:
    the final path is still resolved inside the worktree by the
    harness.
    """
    import os as _os

    if not _os.path.isabs(path):
        return path
    path_real = _os.path.realpath(path)
    ws_real = _os.path.realpath(workspace)
    # The worktree is the harness's root: a path under it rewrites to
    # its workspace-relative form directly.
    rel_ws = _os.path.relpath(path_real, ws_real)
    if not (rel_ws == "." or rel_ws.startswith("..")):
        return rel_ws
    # The primary checkout maps 1:1 onto the worktree layout: a path
    # under it rewrites to the same path relative to the repo root.
    if repo_path:
        repo_real = _os.path.realpath(repo_path)
        rel_repo = _os.path.relpath(path_real, repo_real)
        if not (rel_repo == "." or rel_repo.startswith("..")):
            return rel_repo
    return _strip_bogus_absolute_prefix(path_real, ws_real)


def _normalize_tool_path_args(
    args: dict,
    workspace: str,
    repo_path: str | None,
) -> dict:
    """Rewrite absolute path args to workspace-relative before dispatch."""
    path_keys = ("path", "file_path", "cwd")
    updated = dict(args)
    for key in path_keys:
        value = updated.get(key)
        if isinstance(value, str) and value:
            updated[key] = _relative_to_workspace(value, workspace, repo_path)
    return updated


def _resolve_project(
    user_id: int, project_name: str | None,
) -> tuple[str, str] | None:
    """Return (real_name, workspace_root) for a project reference.

    Matches the named project first; when the name is missing or
    doesn't match but the user has exactly one registered project,
    falls back to it — the model frequently omits ``project_name`` or
    guesses it, and with a single project the intent is unambiguous.
    Returns None when nothing resolves.
    """
    if project_name and project_name.strip():
        projects = HeadlesscodeProject.objects.filter_by(
            user_id=user_id, name=project_name.strip(),
        )
        if projects:
            return projects[0].name, projects[0].workspace_root
    fallback = _single_project_fallback(user_id)
    if fallback is not None:
        return fallback[0][0], fallback[0][1]
    return None


__all__ = [
    "PROJECT_PARAM",
    "_normalize_tool_path_args",
    "_registered_projects",
    "_relative_to_workspace",
    "_resolve_project",
    "_single_project_fallback",
    "_strip_bogus_absolute_prefix",
    "run_async",
]
