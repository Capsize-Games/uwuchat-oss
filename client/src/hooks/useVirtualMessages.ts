import {
  useState,
  useRef,
  useEffect,
  useLayoutEffect,
  useCallback,
} from "react";

/** Default estimated height in px for a message bubble before measurement. */
const ESTIMATED_HEIGHT = 100;
/** Extra messages to render above and below the visible viewport. */
const DEFAULT_OVERSCAN = 5;

export interface VirtualMessagesResult {
  /** [startIndex, endIndex] inclusive, or null when there are no messages. */
  visibleRange: [number, number] | null;
  /** Padding to reserve space for messages above the visible range (px). */
  paddingTop: number;
  /** Padding to reserve space for messages below the visible range (px). */
  paddingBottom: number;
  /**
   * Callback-ref factory. Call `measureRef(index)` inside the render for each
   * message and attach the returned ref to the message's outermost element.
   */
  measureRef: (index: number) => (el: HTMLElement | null) => void;
  /** Programmatically scroll so that the message at `index` is at the top. */
  scrollToIndex: (index: number) => void;
  /**
   * Scroll to the bottom of the message list.  Forces the full message list
   * to mount (bypassing the estimate-based virtualisation cutoff) so that
   * `scrollHeight` reflects real measured heights rather than guesses, then
   * snaps `scrollTop` to true bottom in a single write.
   */
  scrollToBottom: () => void;
}

function computeVisibleRange(
  messageCount: number,
  scrollTop: number,
  containerHeight: number,
  overscan: number,
  heights: Map<number, number>,
): [number, number] | null {
  if (messageCount === 0) return null;

  let acc = 0;
  let start = 0;
  const viewTop = scrollTop;
  const viewBottom = scrollTop + containerHeight;
  let foundStart = false;

  for (let i = 0; i < messageCount; i++) {
    const h = heights.get(i) ?? ESTIMATED_HEIGHT;
    const itemBottom = acc + h;

    if (!foundStart && itemBottom >= viewTop) {
      start = Math.max(0, i - overscan);
      foundStart = true;
    }

    if (itemBottom > viewBottom) {
      const end = Math.min(messageCount - 1, i + overscan);
      return [start, end];
    }

    acc += h;
  }

  // Scrolled past all items — show the tail.
  return [start, messageCount - 1];
}

function computePaddingTop(
  visibleRange: [number, number] | null,
  heights: Map<number, number>,
): number {
  if (!visibleRange) return 0;
  const [start] = visibleRange;
  let top = 0;
  for (let i = 0; i < start; i++) {
    top += heights.get(i) ?? ESTIMATED_HEIGHT;
  }
  return top;
}

function computePaddingBottom(
  visibleRange: [number, number] | null,
  messageCount: number,
  heights: Map<number, number>,
): number {
  if (!visibleRange) return 0;
  const [, end] = visibleRange;
  let bottom = 0;
  for (let i = end + 1; i < messageCount; i++) {
    bottom += heights.get(i) ?? ESTIMATED_HEIGHT;
  }
  return bottom;
}

/**
 * Virtual-scroll helper for a vertical message list with variable heights.
 *
 * Only messages whose indices fall inside `visibleRange` should be rendered.
 * Apply `paddingTop` / `paddingBottom` as spacer `<div>`s inside the scrolling
 * container so the scrollbar stays correct.
 */
export function useVirtualMessages({
  messageCount,
  containerRef,
  overscan = DEFAULT_OVERSCAN,
}: {
  messageCount: number;
  containerRef: React.RefObject<HTMLDivElement | null>;
  overscan?: number;
}): VirtualMessagesResult {
  // ── Stored message heights (state so reads during render are valid) ─────
  const [heights, setHeights] = useState<Map<number, number>>(() => new Map());
  const observersRef = useRef<Map<number, ResizeObserver>>(new Map());
  // DOM element refs stored per-index so the tail-priming useLayoutEffect
  // can read heights synchronously via getBoundingClientRect.
  const elementRefs = useRef<Map<number, HTMLElement>>(new Map());

  // ── Scroll / container geometry ─────────────────────────────────────────
  const [scrollTop, setScrollTop] = useState(0);
  const [containerHeight, setContainerHeight] = useState(0);

  // ── Bottom-pin state — see scrollToBottom() ─────────────────────────────
  const [pinnedToBottom, setPinnedToBottom] = useState(false);

  // ── One-time tail pre-measurement ─────────────────────────────────────
  // When a conversation loads, the last TAIL_BUFFER messages are mounted
  // once so their real heights replace ESTIMATED_HEIGHT guesses in
  // paddingBottom, decoupled from scroll events entirely.  After one
  // animation frame the range contracts back to normal virtualisation.
  const TAIL_BUFFER = 20;
  const [tailPriming, setTailPriming] = useState(false);
  const tailPrimedRef = useRef(false);

  // Boundary-relative "at bottom" tracking for the ResizeObserver
  // compensation below.  Updated on every scroll event.
  const isAtBottomRef = useRef(true);
  const lastMaxScrollRef = useRef(0);

  // Seed containerHeight synchronously before first paint so
  // computeVisibleRange never runs with containerHeight=0 (which
  // produces [0, overscan] — only the first few messages).
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ch = el.clientHeight;
    if (ch > 0 && ch !== containerHeight) {
      setContainerHeight(ch);
    }
    // Only fire on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerRef]);

  // ── Reset height cache + trigger tail pre-measurement on conversation
  //    load ──────────────────────────────────────────────────────────────
  const prevCountRef = useRef(messageCount);
  useEffect(() => {
    if (messageCount === 0 && prevCountRef.current !== 0) {
      for (const ob of observersRef.current.values()) ob.disconnect();
      observersRef.current.clear();
      setHeights(new Map());
      tailPrimedRef.current = false;
    }
    // One-time tail pre-measurement: when a conversation first loads,
    // mount the last TAIL_BUFFER messages so their real heights replace
    // ESTIMATED_HEIGHT guesses in paddingBottom.
    if (messageCount > 0 && !tailPrimedRef.current) {
      tailPrimedRef.current = true;
      setTailPriming(true);
    }
    prevCountRef.current = messageCount;
  }, [messageCount]);

  // ── Synchronous tail measurement ─────────────────────────────────────
  // When tailPriming is active, read heights from the just-committed
  // layout via getBoundingClientRect() inside useLayoutEffect — this is
  // deterministic and doesn't depend on ResizeObserver callback timing,
  // which may not fire before the elements unmount in a one-shot pass.
  useLayoutEffect(() => {
    if (!tailPriming) return;
    const start = Math.max(0, messageCount - TAIL_BUFFER);
    const next = new Map(heights);
    let measured = 0;
    for (let i = start; i < messageCount; i++) {
      const el = elementRefs.current.get(i);
      if (!el) continue;
      const h = el.getBoundingClientRect().height;
      if (h > 0) {
        next.set(i, h);
        measured++;
      }
    }
    setHeights(next);
    setTailPriming(false);
  }, [tailPriming, messageCount, heights]);

  // ── Listen to scroll & container resize ─────────────────────────────────
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const onScroll = () => {
      const st = el.scrollTop;
      setScrollTop(st);
      isAtBottomRef.current =
        st >= lastMaxScrollRef.current - 2;
      lastMaxScrollRef.current =
        el.scrollHeight - el.clientHeight;
    };
    el.addEventListener("scroll", onScroll, { passive: true });

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerHeight(entry.contentRect.height);
      }
    });
    ro.observe(el);

    // Seed geometry without forcing a synchronous layout read.
    // ResizeObserver delivers the first measurement on the next frame.
    const frame = requestAnimationFrame(() => {
      const current = containerRef.current;
      if (current) {
        setScrollTop(current.scrollTop);
        setContainerHeight(current.clientHeight);
      }
    });

    return () => {
      cancelAnimationFrame(frame);
      el.removeEventListener("scroll", onScroll);
      ro.disconnect();
    };
  }, [containerRef]);

  // ── Compensate for content height changes after scroll ─────────────
  // When a message's content grows (e.g. cost annotation populating
  // 1.5s after a bot reply), measureRef's per-message ResizeObserver
  // fires, updating `heights`.  If the user was at bottom when the
  // last scroll event fired, re-snap synchronously before paint.
  // Safe to reintroduce after Round 7 removed the scrollTop-dependent
  // tail-guard that caused Round 6's oscillation.
  useLayoutEffect(() => {
    if (!isAtBottomRef.current) return;
    const el = containerRef.current;
    if (!el) return;
    // Only move forward — never pull the user backward.  Compare the
    // new maxScroll (scrollHeight - clientHeight) against the current
    // scrollTop, not raw scrollHeight vs scrollTop (which is always
    // true because scrollHeight ≈ scrollTop + clientHeight).
    const newMax = el.scrollHeight - el.clientHeight;
    if (newMax > el.scrollTop) {
      el.scrollTop = el.scrollHeight;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [heights]);


  // ── measureRef factory (stable ref) ─────────────────────────────────────
  // React Compiler auto-memoizes this.
  const measureRef = (index: number) => (el: HTMLElement | null) => {
    // Store / remove the element ref for synchronous height reads.
    if (el) {
      elementRefs.current.set(index, el);
    } else {
      elementRefs.current.delete(index);
    }

    // Clean up any previous observer for this index.
    const prevOb = observersRef.current.get(index);
    if (prevOb) {
      prevOb.disconnect();
      observersRef.current.delete(index);
    }

    if (!el) return; // Element unmounted — keep last-known height.

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const h =
          entry.borderBoxSize?.[0]?.blockSize ?? entry.contentRect.height;
        if (h <= 0) continue;
        setHeights((prev) => {
          const old = prev.get(index);
          // Tolerate sub-pixel noise — a remount of the same message
          // can produce slightly different measurements (< 1px) and
          // trigger unnecessary visibleRange recomputation.
          if (old !== undefined && Math.abs(old - h) < 1) return prev;
          const next = new Map(prev);
          next.set(index, h);
          return next;
        });
      }
    });
    observer.observe(el);
    observersRef.current.set(index, observer);
  };

  // ── Derived values (React Compiler handles memoization) ─────────────────
  const rawVisibleRange = computeVisibleRange(
    messageCount,
    scrollTop,
    containerHeight,
    overscan,
    heights,
  );

  // ── Start-boundary hysteresis ───────────────────────────────────────
  // Prevent a message sitting at the visibleRange boundary from
  // flapping in/out of the mounted set due to sub-pixel measurement
  // noise or tiny scrollTop fluctuations.  Only allow start to change
  // when the new value differs meaningfully (more than overscan).
  const lastStartRef = useRef<number | null>(null);
  let visibleStart: number | null = null;
  let visibleEnd: number | null = null;
  if (rawVisibleRange) {
    const [rawStart, rawEnd] = rawVisibleRange;
    if (
      lastStartRef.current !== null &&
      Math.abs(rawStart - lastStartRef.current) <= overscan
    ) {
      visibleStart = lastStartRef.current;
    } else {
      visibleStart = rawStart;
      lastStartRef.current = rawStart;
    }
    visibleEnd = rawEnd;
  }

  const stableVisibleRange: [number, number] | null =
    visibleStart !== null && visibleEnd !== null
      ? [visibleStart, visibleEnd]
      : null;

  // When tailPriming, mount only the last TAIL_BUFFER messages so their
  // real heights are measured without mounting the entire list.
  // When pinnedToBottom (scrollToBottom call), mount everything.
  const isExpanded = tailPriming || pinnedToBottom;
  const visibleRange: [number, number] | null = tailPriming
    ? messageCount > 0
      ? [Math.max(0, messageCount - TAIL_BUFFER), messageCount - 1]
      : null
    : pinnedToBottom
      ? messageCount > 0
        ? [0, messageCount - 1]
        : null
      : stableVisibleRange;

  const paddingTop = isExpanded
    ? 0
    : computePaddingTop(visibleRange, heights);

  const paddingBottom = isExpanded
    ? 0
    : computePaddingBottom(visibleRange, messageCount, heights);

  // ── scrollToIndex ───────────────────────────────────────────────────────
  const scrollToIndex = (index: number) => {
    const el = containerRef.current;
    if (!el) return;
    let offset = 0;
    for (let i = 0; i < index; i++) {
      offset += heights.get(i) ?? ESTIMATED_HEIGHT;
    }
    el.scrollTop = offset;
  };

  // ── scrollToBottom ──────────────────────────────────────────────────────
  const scrollToBottom = useCallback(() => {
    setPinnedToBottom(true);
  }, []);

  // When pinnedToBottom transitions to true, wait one animation frame for
  // the expanded render to commit and layout, then read the (now-accurate)
  // scrollHeight and snap to bottom.
  useEffect(() => {
    if (!pinnedToBottom) return;
    const el = containerRef.current;
    if (!el) {
      setPinnedToBottom(false);
      return;
    }
    const frame = requestAnimationFrame(() => {
      const current = containerRef.current;
      if (current) {
        current.scrollTop = current.scrollHeight;
      }
      setPinnedToBottom(false);
    });
    return () => cancelAnimationFrame(frame);
    // Only react to the pinnedToBottom toggle itself — heights changes
    // during the expanded render must not re-trigger this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pinnedToBottom]);

  return {
    visibleRange,
    paddingTop,
    paddingBottom,
    measureRef,
    scrollToIndex,
    scrollToBottom,
  };
}
