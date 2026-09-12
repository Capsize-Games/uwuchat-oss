import { useState, useRef, useEffect } from "react";

/**
 * Smooth character-by-character typewriter reveal hook.
 *
 * Takes a `source` string that grows in real time (e.g. an LLM stream
 * buffer) and emits a `revealed` substring that catches up toward it at
 * a natural per-character pace, never waiting for the source to stop
 * growing and never snapping unrevealed text into view.
 *
 * Uses a requestAnimationFrame loop with delta-time-based fractional
 * character accrual so pacing adapts smoothly to variable frame timing.
 *
 * Returns `{ revealed, caughtUp }` where:
 *  - `revealed` is the portion of source that should be visible right now
 *  - `caughtUp` is true once `revealed.length === source.length`
 */
export function useTypewriterReveal(
  source: string,
  active: boolean,
): { revealed: string; caughtUp: boolean } {
  const [revealed, setRevealed] = useState("");

  // Number of characters from source that have been revealed so far.
  const revealedLenRef = useRef(0);
  // Fractional character "credit" accumulator — carries over sub-char
  // deltas from frame to frame so pacing stays smooth.
  const creditRef = useRef(0);
  // Timestamp (performance.now) of the last animation frame.
  const lastTsRef = useRef(0);
  // The current requestAnimationFrame id, for cleanup.
  const rafIdRef = useRef(0);

  // ── Tunable reveal pacing constants ─────────────────────────────────
  const BASE_CHARS_PER_SEC = 45;
  const MAX_CHARS_PER_SEC = 400;
  const CATCHUP_BACKLOG_THRESHOLD = 60; // chars
  const CATCHUP_SCALE = 4; // extra chars/sec per char of backlog above threshold

  useEffect(() => {
    // ── Reset detection ──────────────────────────────────────────────
    // If source got shorter (e.g. streamBuffer reset to "" for a new
    // message), reset the reveal back to the start.
    if (source.length < revealedLenRef.current) {
      revealedLenRef.current = 0;
      creditRef.current = 0;
      lastTsRef.current = 0;
      setRevealed("");
    }

    // ── Animation frame loop ─────────────────────────────────────────
    function tick(now: number) {
      if (lastTsRef.current === 0) {
        lastTsRef.current = now;
      }

      const dt = now - lastTsRef.current; // ms since last frame
      lastTsRef.current = now;

      const backlog = source.length - revealedLenRef.current;

      if (backlog > 0) {
        // Compute effective reveal rate for this frame.
        let rate = BASE_CHARS_PER_SEC;
        if (backlog > CATCHUP_BACKLOG_THRESHOLD) {
          rate = Math.min(
            MAX_CHARS_PER_SEC,
            BASE_CHARS_PER_SEC +
              (backlog - CATCHUP_BACKLOG_THRESHOLD) * CATCHUP_SCALE,
          );
        }

        // Accrue fractional characters.
        creditRef.current += rate * (dt / 1000);
        const wholeChars = Math.floor(creditRef.current);

        if (wholeChars > 0) {
          creditRef.current -= wholeChars;
          const newLen = Math.min(
            revealedLenRef.current + wholeChars,
            source.length,
          );
          revealedLenRef.current = newLen;
          setRevealed(source.slice(0, newLen));
        }
      }

      // Keep scheduling frames as long as we're active or there's still
      // backlog to drain. This lets the reveal animate smoothly to
      // completion even after `active` flips false (stream ended).
      const stillHasBacklog = source.length > revealedLenRef.current;
      if (active || stillHasBacklog) {
        rafIdRef.current = requestAnimationFrame(tick);
      }
    }

    // Start the loop if we're active or have backlog to drain.
    const hasBacklog = source.length > revealedLenRef.current;
    if (active || hasBacklog) {
      rafIdRef.current = requestAnimationFrame(tick);
    }

    // ── Cleanup ──────────────────────────────────────────────────────
    return () => {
      if (rafIdRef.current !== 0) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = 0;
      }
    };
  }, [source, active]);

  const caughtUp = revealed.length === source.length && source.length > 0;

  return { revealed, caughtUp };
}
