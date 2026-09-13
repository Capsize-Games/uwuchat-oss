"""UwUChat in-character fallback when the model produced no final text.

Called by the framework's ``_tool_only_fallback`` via a guarded import
(see ``generation_response_support.py``).  The framework's generic
diagnostic text ("The model used non-mutating tools...") is surfaced
verbatim to end users when this module is absent — this override
replaces it with an in-character acknowledgment that never exposes
tool names or internal workflow details.
"""

from __future__ import annotations

# The code-mode proxy tools (see tools/code_tools/).  When the executed
# set includes any of these, the fallback switches to a code-mode-aware
# line instead of the generic companion acknowledgment.
_CODE_MODE_TOOLS = frozenset({
    "apply_diff",
    "codebase_search",
    "edit_file",
    "execute_command",
    "launch_headlesscode_session",
    "list_files",
    "list_registered_projects",
    "read_file",
    "run_tests",
    "search_replace",
    "write_to_file",
})

_GENERIC_LINE = (
    "I looked into that but I'm not quite sure what to make of it "
    "yet — maybe try asking in a slightly different way?"
)

_CODE_MODE_LINE = (
    "I tried to run that on the project but it didn't go through — "
    "the command may not have completed cleanly. Check that the "
    "project is registered in your settings, then try again."
)


def uwuchat_fallback_response(executed_tools: list[str]) -> str:
    """Return an in-character fallback when the model produced no text.

    When the executed tool set includes code-mode tools, returns a
    code-mode-appropriate line; otherwise the generic companion line.
    Never exposes raw tool names or internal workflow diagnostics.

    Args:
        executed_tools: Tool names the model called this turn.

    Returns:
        An in-character fallback string.
    """
    if _CODE_MODE_TOOLS.intersection(executed_tools):
        return _CODE_MODE_LINE
    return _GENERIC_LINE


__all__ = ["uwuchat_fallback_response"]
