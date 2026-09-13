"""File-edit proxy tools: write/edit headlesscode executor tools.

Sibling to ``proxy_tools.py`` — the write/edit tools are split into their
own module so each file stays under the 250-line limit. All
implementations live in the headlesscode harness; these are thin
wrappers over ``POST /api/tool/execute`` only (see
plans/uwuchat-code-mode-agent-tools.md).
"""

from __future__ import annotations

from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import ToolCategory, tool

from projects.uwuchat.server.tools.code_tools._proxy_helpers import (
    PROJECT_PARAM,
    call_tool,
)


@tool(
    name="write_to_file",
    category=ToolCategory.CODE,
    description=(
        "Write (create or overwrite) a file in the registered project's "
        "worktree. Paths relative to the worktree root; outside is refused."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=["write", "create", "file", "overwrite"],
    input_examples=[{"project_name": "acme-web", "path": "notes.txt", "content": "hi"}],
)
def write_to_file(
    project_name: Annotated[
        str | None,
        PROJECT_PARAM + " Optional when you have one project.",
    ] = None,
    path: Annotated[str | None, "File path relative to the worktree root."] = None,
    content: Annotated[str | None, "Full file content to write."] = None,
    agent: Any = None,
) -> str:
    """Write a file in the project's worktree via the harness."""
    return call_tool(
        agent, project_name, "write_to_file", {"path": path, "content": content},
    )


@tool(
    name="apply_diff",
    category=ToolCategory.CODE,
    description=(
        "Apply a unified-diff-style edit to a file in the registered "
        "project's worktree. Follows headlesscode's apply_diff semantics."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=["edit", "diff", "patch", "modify"],
    input_examples=[{"project_name": "acme-web", "path": "src/a.ts", "diff": "..."}],
)
def apply_diff(
    project_name: Annotated[
        str | None,
        PROJECT_PARAM + " Optional when you have one project.",
    ] = None,
    path: Annotated[str | None, "File path relative to the worktree root."] = None,
    diff: Annotated[str | None, "Unified diff text to apply."] = None,
    agent: Any = None,
) -> str:
    """Apply a diff to a file in the project's worktree via the harness."""
    return call_tool(agent, project_name, "apply_diff", {"path": path, "diff": diff})


@tool(
    name="search_replace",
    category=ToolCategory.CODE,
    description=(
        "Replace one exact occurrence of text in a file in the registered "
        "project's worktree (strict literal match)."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=["replace", "edit", "find"],
    input_examples=[
        {
            "project_name": "acme-web",
            "file_path": "src/a.ts",
            "old_string": "foo",
            "new_string": "bar",
        },
    ],
)
def search_replace(
    project_name: Annotated[
        str | None,
        PROJECT_PARAM + " Optional when you have one project.",
    ] = None,
    file_path: Annotated[str | None, "File path relative to the worktree root."] = None,
    old_string: Annotated[str | None, "Exact text to find."] = None,
    new_string: Annotated[str | None, "Replacement text."] = None,
    agent: Any = None,
) -> str:
    """Strict literal replace in a file in the project's worktree."""
    return call_tool(
        agent,
        project_name,
        "search_replace",
        {
            "file_path": file_path,
            "old_string": old_string,
            "new_string": new_string,
        },
    )


@tool(
    name="edit_file",
    category=ToolCategory.CODE,
    description=(
        "Edit a file in the registered project's worktree with fuzzy "
        "matching (falls back exact -> whitespace-tolerant -> token-based)."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=["edit", "modify", "replace"],
    input_examples=[
        {
            "project_name": "acme-web",
            "file_path": "src/a.ts",
            "old_string": "foo",
            "new_string": "bar",
        },
    ],
)
def edit_file(
    project_name: Annotated[
        str | None,
        PROJECT_PARAM + " Optional when you have one project.",
    ] = None,
    file_path: Annotated[str | None, "File path relative to the worktree root."] = None,
    old_string: Annotated[str | None, "Text to replace."] = None,
    new_string: Annotated[str | None, "Replacement text."] = None,
    expected_replacements: Annotated[
        int | None, "Expected number of replacements, if known.",
    ] = None,
    agent: Any = None,
) -> str:
    """Fuzzy edit a file in the project's worktree via the harness."""
    args: dict[str, Any] = {
        "file_path": file_path,
        "old_string": old_string,
        "new_string": new_string,
    }
    if expected_replacements is not None:
        args["expected_replacements"] = expected_replacements
    return call_tool(agent, project_name, "edit_file", args)


__all__ = ["apply_diff", "edit_file", "search_replace", "write_to_file"]
