"""Thin proxy tools: run headlesscode executor tools from UwUChat code mode.

Each ``@tool`` here is a tiny synchronous wrapper over the dashboard's
``POST /api/tool/execute`` (headlesscode's ``tool-exec.ts``). The actual
tool implementations — argument schemas, workspace path safety, command
allow/deny + protected-file permissions, output truncation — all live in
the headlesscode harness; this module deliberately re-implements NONE of
it (see plans/uwuchat-code-mode-agent-tools.md).

Calls run against the registered project's disposable worktree
(``HeadlesscodeProject.workspace_root``), never the primary checkout.
Shared resolution/execution helpers live in ``_proxy_helpers``; the
write/edit tools live in ``proxy_file_tools`` (both split for the
250-line limit).
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import ToolCategory, tool

from projects.uwuchat.server.tools.code_tools._proxy_helpers import (
    PROJECT_PARAM,
    call_tool,
)


@tool(
    name="execute_command",
    category=ToolCategory.CODE,
    description=(
        "Run a shell command inside the registered project's worktree. "
        "Use this to run CLI tools (git, gh, npm, tests, scripts) against "
        "a project the user has registered. Output is truncated harness-side."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=["command", "shell", "bash", "terminal", "run", "gh", "git"],
    input_examples=[{"project_name": "acme-web", "command": "gh issue list"}],
)
def execute_command(
    project_name: Annotated[
        str | None,
        PROJECT_PARAM + " Optional when you have one project.",
    ] = None,
    command: Annotated[str | None, "Shell command to run."] = None,
    cwd: Annotated[str | None, "Relative subdirectory to run in, if any."] = None,
    timeout: Annotated[int | None, "Timeout in seconds (default 120)."] = None,
    agent: Any = None,
) -> str:
    """Run one shell command in the project's worktree via the harness."""
    args: dict[str, Any] = {"command": command or ""}
    if cwd and not os.path.isabs(cwd):
        args["cwd"] = cwd
    elif cwd:
        # Absolute cwd paths are handled by the harness's workspace
        # scoping (which resolves inside the worktree).  The model
        # sometimes passes the primary-checkout path (repo_path) as an
        # absolute cwd; that is refused by the harness's path-safety.
        # Drop it so the command runs at the worktree root instead of
        # failing with a path-escape error.
        pass
    if timeout is not None:
        args["timeout"] = timeout
    return call_tool(agent, project_name, "execute_command", args)


@tool(
    name="read_file",
    category=ToolCategory.CODE,
    description=(
        "Read a file from the registered project's worktree. "
        "Paths are relative to the worktree root; anything outside it is refused."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=["read", "file", "view", "cat"],
    input_examples=[{"project_name": "acme-web", "path": "src/app.ts"}],
)
def read_file(
    project_name: Annotated[
        str | None,
        PROJECT_PARAM + " Optional when you have one project.",
    ] = None,
    path: Annotated[str | None, "File path relative to the worktree root."] = None,
    offset: Annotated[int | None, "Line offset to start from."] = None,
    limit: Annotated[int | None, "Max lines to return."] = None,
    agent: Any = None,
) -> str:
    """Read a file in the project's worktree via the harness."""
    args: dict[str, Any] = {"path": path}
    if offset is not None:
        args["offset"] = offset
    if limit is not None:
        args["limit"] = limit
    return call_tool(agent, project_name, "read_file", args)


@tool(
    name="list_files",
    category=ToolCategory.CODE,
    description=(
        "List files in the registered project's worktree, optionally "
        "recursively. Paths relative to the worktree root."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=["list", "files", "directory", "ls"],
    input_examples=[{"project_name": "acme-web", "path": ".", "recursive": True}],
)
def list_files(
    project_name: Annotated[
        str | None,
        PROJECT_PARAM + " Optional when you have one project.",
    ] = None,
    path: Annotated[str, "Directory path relative to the worktree root."] = ".",
    recursive: Annotated[bool, "Recurse into subdirectories."] = False,
    agent: Any = None,
) -> str:
    """List files in the project's worktree via the harness."""
    return call_tool(
        agent, project_name, "list_files", {"path": path, "recursive": recursive},
    )


@tool(
    name="codebase_search",
    category=ToolCategory.CODE,
    description=(
        "Search the registered project's codebase for a query. Requires the "
        "project's codesearch index (built by the headlesscode harness); "
        "unindexed workspaces return the harness's error."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=["search", "codebase", "code", "find", "symbol"],
    input_examples=[{"project_name": "acme-web", "query": "auth middleware"}],
)
def codebase_search(
    project_name: Annotated[
        str | None,
        PROJECT_PARAM + " Optional when you have one project.",
    ] = None,
    query: Annotated[str | None, "Search query."] = None,
    agent: Any = None,
) -> str:
    """Search the project's codebase via the harness."""
    return call_tool(agent, project_name, "codebase_search", {"query": query})


@tool(
    name="run_tests",
    category=ToolCategory.CODE,
    description=(
        "Run the registered project's tests via the harness. Language-gated "
        "(registered for TypeScript workspaces); unsupported workspaces "
        "return the harness's standard error."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=["test", "tests", "run tests", "verify"],
    input_examples=[{"project_name": "acme-web", "test_command": "npm test"}],
)
def run_tests(
    project_name: Annotated[
        str | None,
        PROJECT_PARAM + " Optional when you have one project.",
    ] = None,
    test_command: Annotated[str | None, "Optional explicit test command."] = None,
    agent: Any = None,
) -> str:
    """Run tests in the project's worktree via the harness."""
    args: dict[str, Any] = {}
    if test_command:
        args["test_command"] = test_command
    return call_tool(agent, project_name, "run_tests", args)


__all__ = [
    "codebase_search",
    "execute_command",
    "list_files",
    "read_file",
    "run_tests",
]
