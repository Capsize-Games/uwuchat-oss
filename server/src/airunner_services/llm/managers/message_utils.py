"""Shared message-manipulation utilities."""

from __future__ import annotations

from typing import List

from langchain_core.messages import BaseMessage


def truncate_oversized_tool_messages(
    messages: List[BaseMessage],
    max_chars: int = 1000,
) -> None:
    """Truncate oversized ToolMessage content in-place.

    A single large search/newspaper ToolMessage (20-40 KB) can consume
    the token budget on every subsequent turn.  This replaces content
    exceeding *max_chars* with a truncated prefix so the message is
    preserved without paying for the full raw payload each time.

    Args:
        messages: Message list to mutate in-place.
        max_chars: Maximum content length before truncation.
    """
    suffix = "\n\n[content truncated]"
    limit = max_chars - len(suffix)
    if limit <= 0:
        return
    for msg in messages:
        if msg.__class__.__name__ != "ToolMessage":
            continue
        content = getattr(msg, "content", "")
        if not isinstance(content, str) or len(content) <= max_chars:
            continue
        truncated = content[:limit] + suffix
        try:
            object.__setattr__(msg, "content", truncated)
        except (AttributeError, TypeError):
            pass


HUMAN_MESSAGE_MAX_CHARS = 50_000


def truncate_oversized_human_message(
    messages: List[BaseMessage],
    max_chars: int = HUMAN_MESSAGE_MAX_CHARS,
) -> None:
    """Truncate the most recent HumanMessage if it exceeds *max_chars*.

    A user can paste an extremely large message (multi-hundred-KB)
    that flows through uncapped because the current turn is never
    trimmed.  This replaces the oversized content with a truncated
    prefix and a note so the user sees what happened, consistent with
    :func:`truncate_oversized_tool_messages`.

    Only the *last* HumanMessage in *messages* is considered — prior
    turns are already handled by ``trim_messages``.
    """
    suffix_fmt = "\n\n[message truncated, {:,d} characters omitted]"
    for msg in reversed(messages):
        if msg.__class__.__name__ != "HumanMessage":
            continue
        content = getattr(msg, "content", "")
        if not isinstance(content, str) or len(content) <= max_chars:
            return
        omitted = len(content) - max_chars
        suffix = suffix_fmt.format(omitted)
        limit = max_chars - len(suffix)
        if limit <= 0:
            limit = max_chars
            suffix = ""
        truncated = content[:limit] + suffix
        try:
            object.__setattr__(msg, "content", truncated)
        except (AttributeError, TypeError):
            pass
        return
