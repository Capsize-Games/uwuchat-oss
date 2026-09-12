"""Materialize Qwen-family embedded tool calls in the agentic workflow.

The local GGUF daemon (Qwen3.5-9B, serving UwUchat code-mode
dialogue) emits tool calls as JSON **inside the message content**
instead of an OpenAI ``tool_calls`` array:

    {"tool_call": {"name": "read_file", "arguments": {...}}}

LangChain's ``bind_tools`` produces an ``AIMessage`` with zero
``tool_calls`` and this JSON as text, so the workflow's route policy
treats every "tool call" as a text-only reply — the model's tool JSON
is delivered as narration and the tool never executes.  This module
detects that embedded JSON and materializes it into real LangChain
``tool_calls`` so the agentic loop routes to the tools node.

Only applies when the message has NO native ``tool_calls`` — native
parsing always wins.  Any parse failure leaves the message untouched
(a content-only reply), so this is a pure no-op on non-Qwen models.
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage

from airunner_services.llm.adapters.mixins.tool_call_payload_helpers import (
    extract_tool_call,
    is_tool_payload,
    normalize_tool_payload,
)

# Fenced JSON block: ```json ... ``` (what the local daemon emits).
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def materialize_embedded_tool_calls(response: AIMessage) -> AIMessage:
    """Return *response* with Qwen embedded tool calls materialized.

    When *response* has no native ``tool_calls`` but its text content
    contains a Qwen ``{"tool_call": ...}`` JSON payload, parse it and
    rebuild the message with real ``tool_calls`` (and the JSON stripped
    from the content).  Otherwise return the message unchanged.
    """
    if getattr(response, "tool_calls", None):
        return response
    content = getattr(response, "content", "")
    if not isinstance(content, str) or not content.strip():
        return response
    tool_calls = _extract_embedded_tool_calls(content)
    if not tool_calls:
        return response
    return AIMessage(
        content="",
        tool_calls=tool_calls,
        additional_kwargs=getattr(response, "additional_kwargs", None) or {},
        id=getattr(response, "id", None),
    )


# Headlesscode narration format the local model falls into when the
# tool-calling grammar isn't strict: ``[Called tool "name" with arguments
# {'command': '...', ...}]`` (Python-dict-like args, single quotes).
_CALLED_TOOL_RE = re.compile(
    r'\[?Called tool ["\']([\w-]+)["\'] with arguments\s+'
    r"(\{.*\})\s*\]?",
    re.DOTALL,
)


def _parse_called_tool_args(raw: str) -> dict | None:
    """Parse a Python-dict-like tool-call argument string into a dict.

    The model narrates args in Python syntax (``{'command': 'grep ...',
    'cwd': None}``).  Converts to JSON (single→double quotes, ``None``→
    ``null``) and parses; on any failure returns None so the message
    stays a content-only reply.
    """
    import ast

    try:
        parsed = ast.literal_eval(raw)
    except (ValueError, SyntaxError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    normalized = {}
    for key, value in parsed.items():
        normalized[str(key)] = value
    return normalized


def _json_candidates(content: str) -> list[str]:
    """Return candidate JSON substrings from *content*.

    Fenced `` ```json {...} ``` `` blocks plus brace-balanced
    substrings that contain ``"tool_call"`` (the bare daemon form).
    """
    candidates: list[str] = []
    for match in _FENCED_JSON_RE.finditer(content):
        candidates.append(match.group(1))
    for start in [i for i, ch in enumerate(content) if ch == "{"]:
        depth = 0
        for end in range(start, len(content)):
            ch = content[end]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = content[start:end + 1]
                    if '"tool_call"' in candidate:
                        candidates.append(candidate)
                    break
    return candidates


def _call_from_json_candidate(raw: str) -> dict | None:
    """Return one LangChain tool-call dict parsed from *raw*, or None."""
    try:
        data = normalize_tool_payload(json.loads(raw))
    except json.JSONDecodeError:
        return None
    if not (isinstance(data, dict) and is_tool_payload(data)):
        return None
    call = extract_tool_call(data)
    if not call.get("name"):
        return None
    return {
        "name": call["name"],
        "args": call.get("args") or {},
        "id": call.get("id") or f"embedded_{len(raw)}",
        "type": "tool_call",
    }


def _call_from_narration(content: str) -> dict | None:
    """Return one tool-call dict parsed from headlesscode narration."""
    match = _CALLED_TOOL_RE.search(content)
    if not match:
        return None
    name = match.group(1)
    args = _parse_called_tool_args(match.group(2))
    if args is None:
        return None
    return {
        "name": name,
        "args": args,
        "id": f"narrated_{len(content)}",
        "type": "tool_call",
    }


def _extract_embedded_tool_calls(content: str) -> list[dict] | None:
    """Return LangChain tool_calls parsed from Qwen embedded JSON, or None.

    Handles the shapes the local daemon emits:
    - fenced `` ```json {"tool_call": {...}} ``` `` blocks,
    - bare ``{"tool_call": {...}}`` objects with nested braces,
    - headlesscode narration ``[Called tool "name" with arguments
      {...}]`` (Python-dict args).
    Any parse failure is skipped (the message stays a content-only
    reply), so this is a pure no-op on ordinary text.
    """
    for raw in _json_candidates(content):
        call = _call_from_json_candidate(raw)
        if call is not None:
            return [call]
    call = _call_from_narration(content)
    if call is not None:
        return [call]
    return None
