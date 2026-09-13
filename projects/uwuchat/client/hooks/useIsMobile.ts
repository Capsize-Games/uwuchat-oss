import { useEffect, useState } from "react";

/** Matches the ContactsSidebar mobile breakpoint at 767px. */
const MOBILE_QUERY = "(max-width: 767px)";

function check(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia(MOBILE_QUERY).matches;
}

/**
 * Returns true when the viewport is ≤ 767 px wide (mobile layout).
 * Re-evaluates on window resize or orientation change.
 */
export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(check);

  useEffect(() => {
    const mql = window.matchMedia(MOBILE_QUERY);
    const handler = (e: MediaQueryListEvent) =>
      setIsMobile(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  return isMobile;
}
