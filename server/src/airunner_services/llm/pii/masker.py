"""Mask PII entities in text and message lists."""

from __future__ import annotations

import logging
from typing import Any, Dict

from airunner_services.llm.pii.analyzer import get_analyzer
from airunner_services.llm.pii.vault import PIIVault

logger = logging.getLogger(__name__)


def mask_text(text: str, vault: PIIVault) -> str:
    """Replace detected PII entities with vault placeholders.

    Builds output by walking through source text linearly, substituting
    placeholder tokens for detected entity spans.  Handles placeholders
    that are longer or shorter than the original entity text.

    When two entity spans overlap, the **longer** span wins and the
    shorter one is discarded (avoids corruption from a person name
    partially inside an email address, for example).

    Empty / whitespace-only input returns unchanged.
    """
    if not text or not text.strip():
        return text

    analyzer = get_analyzer()
    results = analyzer.analyze(text)

    if not results:
        logger.debug("No PII entities found in %d-char text", len(text))
        return text

    # Build (start, end, entity_type, original) tuples.
    spans: list[tuple[int, int, str, str]] = []
    for r in results:
        start = int(r["start"])  # type: ignore[arg-type]
        end = int(r["end"])  # type: ignore[arg-type]
        entity_type = str(r["entity_type"])
        original = text[start:end]
        spans.append((start, end, entity_type, original))

    # Sort by start, then by length descending (longest wins for same
    # start or overlapping).
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))

    # Filter: keep only non-overlapping spans.  When two spans overlap,
    # keep the one that appears first in sorted order (longest for a
    # given start position, earliest start otherwise).
    kept: list[tuple[int, int, str, str]] = []
    last_end = 0
    for start, end, entity_type, original in spans:
        if start < last_end:
            continue  # Overlaps with a previously kept span; skip.
        kept.append((start, end, entity_type, original))
        last_end = end

    # Build output linearly.
    parts: list[str] = []
    pos = 0
    count = 0
    for start, end, entity_type, original in kept:
        if pos < start:
            parts.append(text[pos:start])
        placeholder = vault.placeholder_for(entity_type, original)
        parts.append(placeholder)
        pos = end
        count += 1

    if pos < len(text):
        parts.append(text[pos:])

    result = "".join(parts)
    logger.debug(
        "Masked %d entities in %d-char text -> %d chars",
        count,
        len(text),
        len(result),
    )
    return result


def mask_messages(
    messages: list[Dict[str, str]], vault: PIIVault
) -> list[Dict[str, str]]:
    """Apply ``mask_text`` to every message's ``content`` field.

    Preserves ``role`` and any other keys.  Returns a **new** list —
    the input is never mutated.
    """
    masked: list[dict[str, str]] = []
    for msg in messages:
        new_msg = dict(msg)
        content = new_msg.get("content")
        if isinstance(content, str):
            new_msg["content"] = mask_text(content, vault)
        masked.append(new_msg)

    logger.debug(
        "Masked %d messages (vault size=%d)", len(masked), len(vault),
    )
    return masked


def mask_langchain_messages(
    messages: list[Any], vault: PIIVault
) -> list[Any]:
    """Apply ``mask_text`` to the ``.content`` of each LangChain message.

    Returns a **new** list — does not mutate the input list.
    Each message object is shallow-copied with masked content.
    """
    result: list[Any] = []
    for msg in messages:
        content = getattr(msg, "content", None)
        if isinstance(content, str) and content.strip():
            masked_content = mask_text(content, vault)
            # Use pydantic model_copy to preserve tool_calls, id,
            # response_metadata, type discriminators, etc.
            if hasattr(msg, "model_copy"):
                new_msg = msg.model_copy(
                    update={"content": masked_content}
                )
            elif hasattr(msg, "copy"):
                # pydantic v1 fallback
                new_msg = msg.copy(
                    update={"content": masked_content}
                )
            else:
                # Last resort: reconstruct from __dict__.
                new_msg = msg.__class__(
                    content=masked_content,
                    **{
                        k: v
                        for k, v in msg.__dict__.items()
                        if k != "content" and not k.startswith("_")
                    },
                )
            result.append(new_msg)
        else:
            result.append(msg)

    logger.debug(
        "Masked %d LangChain messages (vault size=%d)",
        len(result),
        len(vault),
    )
    return result
