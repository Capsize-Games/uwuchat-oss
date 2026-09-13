"""Shared relevance check — used by knowledge gate and post-tool helpers.

Extracted from :class:`NodeKnowledgeGate` so the post-tool instruction
path can also check whether tool results actually address the user's
question before instructing the model to synthesize a response.
"""

from __future__ import annotations

from typing import Any, Optional

from langchain_core.messages import HumanMessage


def check_relevance(
    tool_content: str,
    question: str,
    chat_model: Optional[Any],
    logger: Optional[Any] = None,
) -> bool:
    """Return True when *tool_content* is at least partially relevant to
    *question*.

    Uses *chat_model* (a cheap classification model) for the check.
    When no model is available the result defaults to ``True``
    (assume relevance — do not block synthesis when uncertain).

    Args:
        tool_content: The raw tool result text to check.
        question: The user's original question.
        chat_model: A LangChain chat model for classification
            (may be ``None``).
        logger: Optional logger for diagnostics.

    Returns:
        ``True`` when the content appears relevant, ``False``
        when it is clearly unrelated.
    """
    if not question or not tool_content:
        return True
    if chat_model is None:
        return True
    prompt = (
        f'Topic being discussed: "{question[:300]}"\n\n'
        "Retrieved information:\n"
        f"{tool_content[:3000]}\n\n"
        "Does this retrieved information contain anything"
        " useful related to the topic? Answer YES if it is"
        " at least partially relevant. Answer NO only if it"
        " is entirely unrelated to the topic."
        " Answer YES or NO only."
    )
    try:
        resp = chat_model.invoke([HumanMessage(content=prompt)])
        text = str(getattr(resp, "content", "") or "").strip().upper()
        if logger:
            logger.info(
                "relevance=%r for %r", text[:3], question[:50]
            )
        return text.startswith("YES")
    except Exception as exc:
        if logger:
            logger.warning("relevance check error: %s", exc)
        return True
