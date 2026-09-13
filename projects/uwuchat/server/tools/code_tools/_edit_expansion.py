"""Credential-map edit expansion for the code-mode proxy tools.

The local Qwen model frequently emits ``old_string`` / ``new_string``
as structured objects (e.g. ``{"email": ..., "password": ...}``) when
redacting credentials.  The tool-call layer stringifies those objects
to JSON so ToolNode validation passes; these helpers parse them back
and expand the model's "redact these credentials" intent into concrete
literal find/replace pairs, then run each pair through the harness's
``edit_file`` (which replaces ALL occurrences — search_replace is
strict single-occurrence).
"""

from __future__ import annotations

from typing import Any

import httpx

from projects.uwuchat.server.tools.code_tools._path_utils import (
    _normalize_tool_path_args,
    run_async,
)


def _coerce_string_args(args: dict) -> dict:
    """Flatten JSON-serialized object values back into usable strings.

    The tool-call coercion in ``tool_call_args.py`` stringifies
    non-string args so ToolNode validation passes.  A local model that
    emitted ``old_string={"email": "user@example.com", "password":
    "example-lan-password"}`` now arrives as the JSON string
    ``{"email": ..., "password": ...}`` — which is not a literal file
    substring and would fail "no match found".  This helper parses such
    JSON object strings and, for the known credential-map shape
    (``email``/``password`` keys), uses the string values so the
    replacement targets the actual credential text.
    """
    import json as _json

    def _flatten(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        try:
            parsed = _json.loads(value)
        except (_json.JSONDecodeError, TypeError):
            return value
        if not isinstance(parsed, dict):
            return value
        # Credential map: email/password (or user/password) keys — use
        # the values as the literal replacement text.
        values = [
            parsed[key]
            for key in ("email", "user", "password", "username")
            if isinstance(parsed.get(key), str)
        ]
        if values:
            return " ".join(values)
        return value

    return {key: _flatten(value) for key, value in args.items()}


def _found_occurrence_count(result_text: str) -> int | None:
    """Extract the found-occurrence count from an edit_file mismatch error.

    The harness refuses a multi-occurrence ``edit_file`` unless
    ``expected_replacements`` matches exactly, and its error reports the
    count: "Expected 1 occurrence(s) but found 3 exact match(es)."  This
    parses that count so the proxy can retry with the correct value.
    Returns ``None`` when *result_text* is not a count-mismatch error.
    """
    import re as _re

    match = _re.search(r"but found (\d+) (?:exact )?match", result_text)
    if match:
        return int(match.group(1))
    return None


def _as_json_map(value: str | None) -> dict | None:
    """Return *value* parsed as a JSON object, or None."""
    import json as _json

    if not value:
        return None
    try:
        parsed = _json.loads(value)
    except (_json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _expand_credential_replacements(
    old_string: str | None,
    new_string: str | None,
) -> list[tuple[str, str]]:
    """Expand JSON-stringified credential maps into per-key replacements.

    Returns a list of ``(old, new)`` literal replacements.  When
    *old_string* and *new_string* are JSON objects with matching keys
    (e.g. ``{"email": ..., "password": ...}``), one replacement is
    produced per shared key — the model's intent of "redact these
    credentials" is realized as concrete find/replace pairs.  When
    either side is not such a map, the single literal pair is returned
    unchanged.
    """
    old_map = _as_json_map(old_string)
    new_map = _as_json_map(new_string)
    if not old_map or not new_map:
        return [(old_string or "", new_string or "")]
    pairs: list[tuple[str, str]] = []
    for key, old_value in old_map.items():
        new_value = new_map.get(key)
        if isinstance(old_value, str) and isinstance(new_value, str):
            pairs.append((old_value, new_value))
    return pairs or [(old_string or "", new_string or "")]


def _expand_credential_edit(
    args: dict,
    workspace: str,
    repo_path: str | None,
) -> str | None:
    """Run one credential-map edit through the harness; None when not one.

    search_replace / edit_file with credential-map args expand into one
    literal replacement per shared key BEFORE path normalization
    flattens the JSON maps, so the model's "redact these credentials"
    intent becomes concrete find/replace pairs.  edit_file replaces ALL
    occurrences (search_replace is strict single-occurrence), which is
    what a credentials sweep requires.  The harness validates the exact
    occurrence count, so a mismatch error (which reports the found
    count) triggers one retry with the corrected count.
    """
    from projects.uwuchat.server.headlesscode_client import execute_tool

    pairs = _expand_credential_replacements(
        args.get("old_string"), args.get("new_string"),
    )
    if len(pairs) <= 1:
        return None
    outputs: list[str] = []
    for old_value, new_value in pairs:
        pair_args = _normalize_tool_path_args({
            "file_path": args.get("file_path"),
            "old_string": old_value,
            "new_string": new_value,
        }, workspace, repo_path)
        try:
            result = run_async(
                execute_tool(workspace, "edit_file", pair_args)
            )
            content = str(result.get("content") or "")
            found = _found_occurrence_count(content)
            if found is not None:
                result = run_async(execute_tool(workspace, "edit_file", {
                    **pair_args,
                    "expected_replacements": found,
                }))
                content = str(result.get("content") or "")
            outputs.append(content)
        except (httpx.HTTPError, OSError) as exc:
            outputs.append(f"Tool error: {exc}")
    return "\n".join(outputs)


__all__ = [
    "_coerce_string_args",
    "_expand_credential_edit",
    "_expand_credential_replacements",
    "_found_occurrence_count",
]
