"""Streaming placeholder restorer — buffered, incremental de-masking.

Wraps an iterator of text chunks (as produced by the LLM adapter's
``stream()`` method) and yields de-masked chunks.  Holds back a small
trailing buffer so a placeholder token split across two chunks is never
emitted half-restored.

Algorithm: bracket-balance counting — everything before the first
unmatched ``[`` is safe to flush and restore.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from airunner_services.llm.pii.vault import PIIVault

logger = logging.getLogger(__name__)


class StreamingRestorer:
    """Buffered streaming de-masker for LLM text chunks.

    Algorithm
    ---------
    1. Append each incoming chunk to an internal buffer.
    2. Scan the buffer for the **longest prefix** that is provably NOT
       the start of any placeholder pattern — i.e. everything up to the
       last character that could still be part of an opening ``[``.
    3. Flush that prefix through ``restore_text``, yielding de-masked
       output.
    4. Keep the ambiguous suffix (the ``[`` and everything after it) in
       the buffer for the next chunk.
    5. On iterator exhaustion, flush the remaining buffer as-is (even
       if it contains an unresolved ``[`` — treat as literal text).

    This prevents a placeholder like ``[PERSON_1]`` from being split
    between chunks (A: ``"...[PERS"``, B: ``"ON_1]..."``) in a way that
    would cause the restorer to emit a half-placeholder.
    """

    def __init__(self, chunks: Iterator[str], vault: PIIVault) -> None:
        self._chunks = chunks
        self._vault = vault
        self._buffer = ""

    def __iter__(self) -> Iterator[str]:
        return self

    def __next__(self) -> str:
        # Drain upstream chunks into the buffer until we have enough
        # safe content to flush.
        while True:
            # Try to get another chunk.
            try:
                chunk = next(self._chunks)
            except StopIteration:
                # No more chunks — flush whatever is left.
                return self._flush_remainder()

            self._buffer += chunk

            # Find the last safe cut point: everything before the
            # first '[' that might start a placeholder.
            safe = self._find_safe_prefix()
            if safe > 0:
                return self._flush_prefix(safe)

            # If the buffer starts with '[' and we haven't found a safe
            # cut point, keep buffering more chunks (loop continues).

    def _find_safe_prefix(self) -> int:
        """Return the length of the longest safe prefix.

        A safe prefix ends before any character that could be part of
        an incomplete ``[PLACEHOLDER`` pattern.  Specifically, the last
        ``[`` in the buffer (if any) that has not yet been closed by a
        ``]`` marks the start of the unsafe zone.
        """
        if not self._buffer:
            return 0

        # Find all '[' positions and all ']' positions.
        # The last unmatched '[' is the start of the unsafe zone.
        open_positions: list[int] = []
        for i, ch in enumerate(self._buffer):
            if ch == "[":
                open_positions.append(i)
            elif ch == "]":
                if open_positions:
                    open_positions.pop()

        if not open_positions:
            # All brackets are balanced — entire buffer is safe.
            return len(self._buffer)

        # The first unmatched '[' starts the unsafe zone.
        unsafe_start = open_positions[0]
        if unsafe_start == 0:
            return 0  # Entire buffer is potentially a placeholder.
        return unsafe_start

    def _flush_prefix(self, length: int) -> str:
        """Flush *length* chars from the buffer through ``restore_text``."""
        prefix = self._buffer[:length]
        self._buffer = self._buffer[length:]

        # Restore placeholders in this prefix.
        from airunner_services.llm.pii.restorer import restore_text

        return restore_text(prefix, self._vault)

    def _flush_remainder(self) -> str:
        """Flush the remaining buffer (on stream end)."""
        if not self._buffer:
            raise StopIteration
        result = self._buffer
        self._buffer = ""
        from airunner_services.llm.pii.restorer import restore_text

        restored = restore_text(result, self._vault)
        if not restored:
            raise StopIteration
        return restored
