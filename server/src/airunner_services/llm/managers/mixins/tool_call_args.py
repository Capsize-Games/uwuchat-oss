"""Shared tool-call argument normalization helpers.

The local Qwen daemon occasionally emits structured objects for
string-typed tool parameters (e.g. ``search_replace`` with
``old_string={"email": ..., "password": ...}``).  LangChain's ToolNode
validates args against the tool's Pydantic schema and rejects a dict
for a ``str`` field with a generic "Error invoking tool" result, so the
intended edit never runs and the model loops retrying the same call.
These helpers coerce non-string scalar values to compact JSON before
ToolNode so the call reaches the tool, which then normalizes the value
itself.
"""

from __future__ import annotations

import json


def coerce_non_string_tool_args(tool_calls: list[dict]) -> list[dict]:
    """Coerce non-string scalar args to JSON strings for ToolNode.

    Returns a new list with every dict/list/other-scalar arg value
    stringified; plain string args and calls without dict args pass
    through unchanged.
    """
    normalized: list[dict] = []
    for call in tool_calls:
        args = call.get("args")
        if isinstance(args, dict):
            coerced = {
                key: (
                    json.dumps(value, sort_keys=True)
                    if isinstance(value, (dict, list))
                    else str(value) if not isinstance(value, str) else value
                )
                for key, value in args.items()
            }
            normalized.append({**call, "args": coerced})
        else:
            normalized.append(call)
    return normalized


__all__ = ["coerce_non_string_tool_args"]
