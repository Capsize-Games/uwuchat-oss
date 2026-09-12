import { useEffect, useRef, useCallback } from "react";

/** Maximum time (ms) after load to keep chasing the bottom. */
const POST_LOAD_WINDOW = 800;

/**
 * Smart auto-scroll hook that mimics the scroll behavior of Claude, Gemini,
 * and ChatGPT:
 *
 * 1. On initial load / page reload, scroll to the bottom.
 * 2. When streaming starts (user submits), always scroll to bottom.
 * 3. As new tokens stream in, auto-scroll only if the user is already
 *    near the bottom of the container.
 * 4. If the user scrolls up during streaming, auto-scroll is paused.
 * 5. If the user scrolls back to the bottom, auto-scroll resumes.
 *
 * @param containerRef - React ref to the scrollable DOM element.
 * @param isStreaming  - Whether the LLM is currently streaming a response.
 * @param isLoading    - Whether messages are still being loaded.
 * @param deps         - Additional values that should trigger an auto-scroll
 *                       check when they change (e.g. streamBuffer).
 */
export function useAutoScroll(
  containerRef: React.RefObject<HTMLDivElement | null>,
  isStreaming: boolean,
  isLoading: boolean,
  deps: unknown[],
) {
  const userScrolledAwayRef = useRef(false);
  const wasStreamingRef = useRef(isStreaming);
  const wasLoadingRef = useRef(isLoading);

  /** Returns true when the user is within 40 px of the bottom. */
  const isAtBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return true;
    const { scrollTop, scrollHeight, clientHeight } = el;
    return scrollHeight - scrollTop - clientHeight < 40;
  }, [containerRef]);

  /** Snap the container to the bottom immediately. */
  const scrollToBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [containerRef]);

  /** Attach this to the container's `onScroll` handler. */
  const handleScroll = useCallback(() => {
    userScrolledAwayRef.current = !isAtBottom();
  }, [isAtBottom]);

  // ── After load: keep chasing the bottom as virtual-scroll heights
  //    stabilise (ResizeObserver measurements arrive async after first
  //    paint and fire multiple rounds for nested markdown content).
  useEffect(() => {
    if (wasLoadingRef.current && !isLoading) {
      userScrolledAwayRef.current = false;
      const el = containerRef.current;
      if (!el) {
        wasLoadingRef.current = isLoading;
        return;
      }

      let lastScrollHeight = 0;
      let rounds = 0;
      let stopped = false;

      const chase = () => {
        if (stopped) return;
        // RAF before read → browser has applied any pending layout.
        requestAnimationFrame(() => {
          if (stopped) return;
          const sh = el.scrollHeight;
          if (sh !== lastScrollHeight) {
            lastScrollHeight = sh;
            el.scrollTop = sh;
            rounds++;
            if (rounds < 30) {
              requestAnimationFrame(chase);
            }
          }
        });
      };

      // Kick off the chase on the next animation frame.
      requestAnimationFrame(chase);

      // Stop after POST_LOAD_WINDOW to avoid an infinite loop on
      // pages where content genuinely never stabilises.
      const timer = setTimeout(() => {
        stopped = true;
        el.scrollTop = el.scrollHeight;
      }, POST_LOAD_WINDOW);

      wasLoadingRef.current = isLoading;
      return () => {
        stopped = true;
        clearTimeout(timer);
      };
    }
    wasLoadingRef.current = isLoading;
  }, [isLoading, scrollToBottom, containerRef]);

  // ── On streaming start → always scroll to bottom ────────────────
  useEffect(() => {
    if (isStreaming && !wasStreamingRef.current) {
      userScrolledAwayRef.current = false;
      scrollToBottom();
    }
    wasStreamingRef.current = isStreaming;
  }, [isStreaming, scrollToBottom]);

  // ── On content change → auto-scroll unless user scrolled away ───
  useEffect(() => {
    if (!userScrolledAwayRef.current) {
      scrollToBottom();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { scrollToBottom, handleScroll };
}
