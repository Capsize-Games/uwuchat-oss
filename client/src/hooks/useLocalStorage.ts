import { useState, useCallback } from "react";

// ── useLocalStorage ───────────────────────────────────────────────────────────
// Typed localStorage hook with synchronous initialisation (safe for reading on
// first render) and a stable setter that persists on every call.

export function useLocalStorage<T>(
  key: string,
  defaultValue: T,
): [T, (value: T) => void] {
  const [value, setValueState] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw === null) return defaultValue;
      return JSON.parse(raw) as T;
    } catch {
      // Legacy bare-string values stored before JSON encoding was
      // adopted (e.g. "privacy", "mint").  Return them as-is when
      // the caller expects a string default.
      const raw = localStorage.getItem(key);
      if (raw !== null && typeof defaultValue === "string") {
        return raw as unknown as T;
      }
      return defaultValue;
    }
  });

  const setValue = useCallback(
    (next: T) => {
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch { /* quota */ }
      setValueState(next);
    },
    [key],
  );

  return [value, setValue];
}
