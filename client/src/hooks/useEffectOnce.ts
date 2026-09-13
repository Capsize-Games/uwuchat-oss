import { type EffectCallback, useEffect } from "react";

/** Run *effect* once per component mount.  This is a thin wrapper
 *  around ``useEffect(effect, [])`` that correctly supports React
 *  StrictMode double-invocation: each mount gets its own freshly
 *  scoped closure, so the second (real) invocation is not blocked.
 *
 *  Supports cleanup functions (returned from *effect*) the same way
 *  ``useEffect`` does.
 *
 *  Only use for mount-time read-only fetches with the standard
 *  ``let cancelled = false; ... return () => { cancelled = true; }``
 *  pattern.  Do NOT use for effects that perform one-shot mutations
 *  or side effects that must not run twice. */
export function useEffectOnce(effect: EffectCallback): void {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const cleanup = effect();
    // Only return a cleanup if it's actually a function — an async
    // effect returns a Promise, which React would try to call as
    // `destroy()`, crashing the component.
    if (typeof cleanup === "function") return cleanup;
  }, []);
}
