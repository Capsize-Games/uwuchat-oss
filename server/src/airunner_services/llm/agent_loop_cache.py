"""Prompt-cache injection for iterative agent / tool-execution loops.

Unlike the DIALOGUE path (which goes through ``NodePromptCacheMixin``
and adds ``cache_control`` markers on the system prompt and pre-turn
history), these loops build ``[SystemMessage, HumanMessage]`` directly
and accumulate ``AIMessage`` / ``ToolMessage`` pairs on each iteration.
This module provides a standalone helper to inject a ``cache_control``
marker on the last message before each subsequent LLM call so the
provider can serve the unchanged prefix from cache.
"""

from __future__ import annotations

from typing import List

from langchain_core.messages import BaseMessage


def inject_agent_loop_cache_breakpoint(
    messages: List[BaseMessage],
) -> List[BaseMessage]:
    """Mark the last message with ``cache_control`` for iterative loops.

    In a growing agent loop::

        [System, Human]                    # round 0 — all new
        [System, Human, AI, Tool]          # round 1 — cache System+Human
        [System, Human, AI, Tool, AI, Tool] # round 2 — cache through prev

    This function marks the **last** message in *messages* with
    ``cache_control: {"type": "ephemeral"}`` so that on the next LLM
    call everything up to that point can be served from cache.  Callers
    should invoke this on a copy of the message list right before
    calling the model; the original list is never mutated.

    Returns a **new** list.  Messages already carrying a
    ``cache_control`` content block are returned unchanged.
    """
    if not messages:
        return list(messages)

    last = messages[-1]
    content = getattr(last, "content", None)

    # Already tagged — nothing to do.
    if isinstance(content, list) and any(
        isinstance(b, dict) and "cache_control" in b
        for b in content
    ):
        return list(messages)

    # Build the cache_control-tagged content block.
    if isinstance(content, str):
        tagged: list[dict] = [{
            "type": "text",
            "text": content,
            "cache_control": {"type": "ephemeral"},
        }]
    elif isinstance(content, list):
        tagged = list(content)
        if tagged:
            tagged[-1] = {
                **tagged[-1],
                "cache_control": {"type": "ephemeral"},
            }
    else:
        tagged = [{
            "type": "text",
            "text": str(content or ""),
            "cache_control": {"type": "ephemeral"},
        }]

    new_msg = last.model_copy(update={"content": tagged})
    result = list(messages)
    result[-1] = new_msg
    return result


def compute_message_char_count(
    messages: List[BaseMessage],
) -> int:
    """Return the total character count of all message contents.

    Used as an inexpensive approximation of prompt size for
    ``prompt_char_count`` logging in agent loops — avoids the
    overhead of a full tokenization pass while still reflecting
    real message-list growth across iterations.
    """
    total = 0
    for msg in messages:
        content = getattr(msg, "content", None)
        if content is None:
            continue
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += len(block.get("text", ""))
                else:
                    total += len(str(block))
        else:
            total += len(str(content))
    return total
