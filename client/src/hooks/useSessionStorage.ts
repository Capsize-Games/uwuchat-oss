import { useState, useCallback } from "react";

// ── useSessionStorage ────────────────────────────────────────────────────────
// Typed sessionStorage hook with synchronous initialisation (safe for reading
// on first render) and a stable setter that persists on every call.
// SessionStorage is cleared when the tab is closed, limiting the exposure
// window for bearer secrets like API keys.

export function useSessionStorage<T>(
  key: string,
  defaultValue: T,
): [T, (value: T) => void] {
  const [value, setValueState] = useState<T>(() => {
    try {
      const raw = sessionStorage.getItem(key);
      if (raw === null) return defaultValue;
      return JSON.parse(raw) as T;
    } catch {
      return defaultValue;
    }
  });

  const setValue = useCallback(
    (next: T) => {
      try {
        sessionStorage.setItem(key, JSON.stringify(next));
      } catch { /* quota */ }
      setValueState(next);
    },
    [key],
  );

  return [value, setValue];
}
