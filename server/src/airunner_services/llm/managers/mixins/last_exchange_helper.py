"""Extract the last human/AI exchange from message history."""

from __future__ import annotations

from typing import List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


def last_exchange_block(messages: List[BaseMessage]) -> str:
    """Return a pinned block with the last human/AI exchange."""
    try:
        last_ai = next(
            (
                m
                for m in reversed(messages)
                if isinstance(m, AIMessage)
                and isinstance(m.content, str)
                and m.content.strip()
            ),
            None,
        )
        if last_ai is None:
            return ""
        ai_idx = (
            len(messages) - 1 - list(reversed(messages)).index(last_ai)
        )
        last_human = next(
            (
                m
                for m in reversed(messages[:ai_idx])
                if isinstance(m, HumanMessage)
                and isinstance(m.content, str)
                and m.content.strip()
            ),
            None,
        )
        if last_human is None:
            return ""
        human_text = str(last_human.content)[:300].strip()
        ai_text = str(last_ai.content)[:300].strip()
        return (
            "[Most recent exchange]\n"
            f"User: {human_text}\n"
            f"Bot: {ai_text}"
        )
    except Exception:
        return ""
