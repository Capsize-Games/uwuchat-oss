"""Shared helpers for the code-mode proxy tools (headlesscode thin proxy).

``run_async`` / ``call_tool`` are used by every proxy tool module; the
path/workspace helpers live in ``_path_utils.py`` and the credential-map
edit expansion lives in ``_edit_expansion.py`` so each module stays
under the 250-line limit.
"""

from __future__ import annotations

from typing import Any

import httpx

from projects.uwuchat.server.tools.code_tools._edit_expansion import (
    _expand_credential_edit,
)
from projects.uwuchat.server.tools.code_tools._path_utils import (
    PROJECT_PARAM,
    _normalize_tool_path_args,
    _registered_projects,
    _resolve_project,
    run_async,
)

__all__ = [
    "PROJECT_PARAM",
    "call_tool",
    "run_async",
]


def unregistered_message(project_name: str, user_id: int) -> str:
    """Build a helpful error listing the user's registered projects."""
    projects = _registered_projects(user_id)
    names = ", ".join(p.name for p in projects) or "none yet"
    return (
        f"'{project_name}' isn't a registered project. Registered "
        f"projects: {names}. The user can add one in settings."
    )


def _host_exec_result(command: str, user: Any) -> str:
    """Route a host-needing command through the consent-gated agent.

    Returns the tool-result string the model sees: the agent's output,
    a denial reason, or a structured consent marker the client renders
    as a consent card (``HOST_EXEC_CONSENT::<json>``).
    """
    from projects.uwuchat.server.host_exec_client import execute
    from projects.uwuchat.server.host_exec_policy import (
        HostExecPolicy,
        classify_group,
        needs_host,
    )

    if not needs_host(command):
        return f"<host-exec> '{command}' is container-safe; run it normally."
    policy = HostExecPolicy.from_user_data(user)
    if not policy.enabled:
        return "<host-exec> host execution is disabled by your policy."
    # Evaluate against the user's policy (mirror of the agent's gate).
    import re as _re

    from projects.uwuchat.server.host_exec_policy import HARD_BLACKLIST

    if any(_re.search(p, command, _re.IGNORECASE) for p in HARD_BLACKLIST):
        return "<host-exec> blocked: command is on the hard blacklist."
    if policy.enable_all or _matches_policy(command, policy):
        return _dispatch_host(command, execute)
    # Needs consent → structured marker for the client consent card.
    import json as _json

    marker = {
        "command": command,
        "group": classify_group(command),
        "needs_consent": True,
    }
    return f"HOST_EXEC_CONSENT::{_json.dumps(marker)}"


def _matches_policy(command: str, policy) -> bool:
    """Return True when a command is whitelisted/allow-always'd."""
    for pattern in policy.whitelist + policy.allow_always:
        if not pattern:
            continue
        if pattern in command or command.startswith(pattern):
            return True
    return False


def _dispatch_host(command: str, execute_fn) -> str:
    """Run one command via the host agent; return the result string."""
    from projects.uwuchat.server.host_exec_client import available

    if not available():
        return "<host-exec> host executor is not running — start scripts/host-executor.py"
    resp = execute_fn(command)
    status = resp.get("status")
    if status == "ok":
        return str(resp.get("output") or "")
    if status == "denied":
        return f"<host-exec> denied: {resp.get('output') or 'no reason'}"
    return f"<host-exec> error: {resp.get('output') or status}"


def _workspace_is_stale(workspace: str | None) -> bool:
    """Return True when *workspace* exists but has no real content.

    A disposable worktree can be left stale/empty (e.g. a session that
    ran as root created only a ``.headlesscode/`` dir, or the worktree
    was removed but the registered ``workspace_root`` still points at
    the leftover dir).  Operating against such a dir makes every file
    tool return "not found" and the agent stall.  A dir that does NOT
    exist is left alone (it is either a not-yet-created worktree or a
    test fake) — only a dir that exists but is empty/scratch-only is
    considered stale.
    """
    import os as _os

    if not workspace or not _os.path.isdir(workspace):
        return False
    if _os.path.isdir(_os.path.join(workspace, ".git")):
        return False
    # A bare dir with only .headlesscode/ is stale — nothing to work on.
    entries = [
        e for e in _os.listdir(workspace)
        if e != ".headlesscode"
    ]
    return not bool(entries)


def _resolve_workspace(
    user_id: int, project_name: str,
) -> tuple[str, str, str, str | None] | str:
    """Return (real_name, workspace, hint, repo_path), or an error string.

    Resolves the registered project, building the "use the real name"
    hint when the model guessed a name, and the primary checkout's
    repo path for path normalization.  When the stored workspace is a
    stale/empty dir (exists but has no source), falls back to the
    project's ``repo_path`` (the primary checkout) so tool calls keep
    working against real code instead of an empty worktree.
    """
    resolved = _resolve_project(user_id, project_name)
    if resolved is None:
        return unregistered_message(project_name, user_id)
    real_name, workspace = resolved
    if (project_name or "").strip() != real_name:
        # The model guessed the name — surface the real one so it
        # learns "airunner" instead of repeating the guess.
        hint = (
            f"[Note: the registered project is named '{real_name}' — "
            "use that name for future calls.]\n"
        )
    else:
        hint = ""

    from projects.uwuchat.server.models.headlesscode_project import (
        HeadlesscodeProject,
    )

    repo_path = None
    projects = HeadlesscodeProject.objects.filter_by(
        user_id=user_id, name=real_name,
    )
    # Defensive: _resolve_project just returned this project, so the
    # filter is never empty here except in a TOCTOU delete race.
    if projects:  # pragma: no cover - unreachable defensive branch
        repo_path = projects[0].repo_path

    if _workspace_is_stale(workspace) and repo_path:
        hint += (
            "[Note: the disposable worktree is empty/stale — falling "
            f"back to the primary checkout at '{repo_path}'.]\n"
        )
        workspace = repo_path
    return real_name, workspace, hint, repo_path


def call_tool(agent: Any, project_name: str, name: str, args: dict) -> str:
    """Resolve the workspace and run one harness tool; return the result."""
    user = getattr(agent, "user", None) if agent else None
    user_id = getattr(user, "id", None) if user else None
    if not user_id:
        return unregistered_message(project_name, 0)
    resolved = _resolve_workspace(user_id, project_name)
    if isinstance(resolved, str):
        return resolved
    _real_name, workspace, hint, repo_path = resolved
    from projects.uwuchat.server.headlesscode_client import execute_tool

    if name in {"search_replace", "edit_file"}:
        expanded = _expand_credential_edit(args, workspace, repo_path)
        if expanded is not None:
            return hint + expanded

    args = _normalize_tool_path_args(args, workspace, repo_path)

    # execute_command with a host-needing command routes to the host agent.
    if name == "execute_command":
        command = str(args.get("command") or "").strip()
        from projects.uwuchat.server.host_exec_policy import needs_host

        if command and needs_host(command):
            return _host_exec_result(command, user)

    try:
        result = run_async(execute_tool(workspace, name, args))
    except (httpx.HTTPError, OSError) as exc:
        return f"Tool error: {exc}"
    return hint + str(result.get("content") or "")
