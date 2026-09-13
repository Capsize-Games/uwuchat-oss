"""Restore original PII values from vault placeholders."""

from __future__ import annotations

import logging

from airunner_services.llm.pii.vault import PIIVault

logger = logging.getLogger(__name__)


def restore_text(text: str, vault: PIIVault) -> str:
    """Replace every vault placeholder in *text* with its original value.

    Unknown placeholders (not in the vault) are left as-is.
    Longest-placeholder-first replacement avoids ``[PERSON_1]``
    matching inside ``[PERSON_10]``.
    """
    if not text or not text.strip():
        return text

    placeholders = vault.all_placeholders_sorted_longest_first()
    if not placeholders:
        return text

    result = text
    count = 0
    for ph in placeholders:
        original = vault.original_for(ph)
        if original is None:
            continue
        if ph in result:
            result = result.replace(ph, original)
            count += 1

    logger.debug(
        "Restored %d placeholders in %d-char text → %d chars",
        count,
        len(text),
        len(result),
    )
    return result
