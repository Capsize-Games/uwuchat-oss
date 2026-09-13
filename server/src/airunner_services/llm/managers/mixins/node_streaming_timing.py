"""Per-chunk timing instrumentation for streamed model calls.

Distinguishes genuine incremental streaming (chunks trickle in over
the whole generation) from provider-side buffering that still yields
many chunks but delivers them all in one burst near the end.
"""

from __future__ import annotations

import time
from typing import Optional


class StreamTiming:
    """Track visible-chunk arrival timing for one streamed response."""

    def __init__(self) -> None:
        self._start = time.monotonic()
        self._first: Optional[float] = None
        self._last: Optional[float] = None
        self._max_gap: float = 0.0

    def record(self) -> None:
        """Record the arrival of one visible-content chunk."""
        now = time.monotonic()
        if self._first is None:
            self._first = now
        elif self._last is not None:
            gap = now - self._last
            if gap > self._max_gap:
                self._max_gap = gap
        self._last = now

    def first_chunk_ms(self) -> Optional[int]:
        """Ms from loop start to the first visible chunk."""
        if self._first is None:
            return None
        return round((self._first - self._start) * 1000)

    def max_gap_ms(self) -> int:
        """Largest gap in ms between two consecutive visible chunks."""
        return round(self._max_gap * 1000)

    def total_ms(self) -> int:
        """Total elapsed ms from loop start to the last visible chunk."""
        end = self._last if self._last is not None else time.monotonic()
        return round((end - self._start) * 1000)
