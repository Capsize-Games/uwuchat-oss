"""Request-scoped, in-memory placeholder ↔ original-value map.

Never persisted.  Never logged.  One instance per LLM request,
discarded when the request finishes.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PIIVault:
    """Bi-directional map between PII placeholders and original values.

    Consistent placeholders: the same literal string maps to the
    same placeholder for the vault's lifetime, so coreference
    (e.g. "tell John and then email him") still works.

    Never log ``original`` or ``placeholder`` string values —
    only counts and entity-type tallies.
    """

    def __init__(self) -> None:
        self._forward: dict[tuple[str, str], str] = {}
        self._reverse: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def __len__(self) -> int:
        """Return the number of distinct entity↔placeholder mappings."""
        return len(self._forward)

    @property
    def size(self) -> int:
        """Alias for ``len(vault)`` — more explicit in logging contexts."""
        return len(self._forward)

    def placeholder_for(self, entity_type: str, original: str) -> str:
        """Return the existing placeholder or mint and record a new one.

        Args:
            entity_type: e.g. ``"PERSON"``, ``"EMAIL_ADDRESS"``.
            original: The literal PII string found in source text.

        Returns:
            A placeholder like ``[PERSON_1]``, consistent across calls.
        """
        key = (entity_type, original)
        if key in self._forward:
            return self._forward[key]
        idx = self._counters.get(entity_type, 0) + 1
        self._counters[entity_type] = idx
        placeholder = f"[{entity_type}_{idx}]"
        self._forward[key] = placeholder
        self._reverse[placeholder] = original
        logger.debug(
            "Minted placeholder type=%s count=%d total=%d",
            entity_type,
            idx,
            len(self._forward),
        )
        return placeholder

    def original_for(self, placeholder: str) -> Optional[str]:
        """Reverse lookup — return original text or ``None`` if unknown.

        Unknown placeholders (e.g. model-hallucinated) must not raise.
        """
        return self._reverse.get(placeholder)

    def all_placeholders_sorted_longest_first(self) -> list[str]:
        """Placeholders sorted longest-first to avoid partial-match bugs.

        Needed when restoring: always try ``[PERSON_10]`` before
        ``[PERSON_1]`` to prevent the latter from matching inside
        the former.
        """
        return sorted(self._reverse.keys(), key=len, reverse=True)
