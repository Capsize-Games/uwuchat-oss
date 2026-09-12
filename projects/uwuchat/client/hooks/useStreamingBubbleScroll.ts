import { useCallback, useRef } from "react";

/**
 * Returns a **callback ref** that, when attached to a streaming-bubble
 * element, observes its height changes via `ResizeObserver` and nudges
 * `scrollTop` forward whenever the bubble grows while the user is
 * scrolled to the bottom.
 *
 * A callback ref is required here (not a `useLayoutEffect` keyed on a
 * stable ref object) because the streaming bubble is conditionally
 * rendered — it does not exist on mount, so an effect that reads
 * `.current` on mount would find `null` and never re-run.
 *
 * Mirrors the monotonic "only move forward" guard from
 * `useVirtualMessages.ts` (lines 247–260) to prevent oscillation.
 *
 * @param containerRef         The scrollable container element.
 * @param userScrolledAwayRef  `true` when the user has manually scrolled
 *                             up; scroll compensation is skipped.
 * @returns A callback ref to spread onto the streaming bubble's
 *          outermost element via JSX `ref`.
 */
export function useStreamingBubbleScroll(
  containerRef: React.RefObject<HTMLDivElement | null>,
  userScrolledAwayRef: React.MutableRefObject<boolean>,
): (el: HTMLDivElement | null) => void {
  const observerRef = useRef<ResizeObserver | null>(null);

  return useCallback(
    (el: HTMLDivElement | null) => {
      // Teardown: disconnect any previous observer (covers unmount +
      // conditional re-mount when the stream restarts).
      observerRef.current?.disconnect();
      observerRef.current = null;
      if (!el) return;

      // Setup: observe the newly-mounted streaming bubble.
      const ro = new ResizeObserver(() => {
        // TODO(diag): remove after scroll-jank fix verification
        console.log("[scroll-diag] uwuchat streaming RO callback at", performance.now());

        if (userScrolledAwayRef.current) return;
        const container = containerRef.current;
        if (!container) return;

        // Monotonic "only move forward" guard — compare the new max
        // scroll position against the current scrollTop, not raw
        // scrollHeight (which is always > scrollTop when content
        // overflows).
        const newMax = container.scrollHeight - container.clientHeight;
        if (newMax > container.scrollTop) {
          container.scrollTop = container.scrollHeight;
        }
      });
      ro.observe(el);
      observerRef.current = ro;
    },
    [containerRef, userScrolledAwayRef],
  );
}
