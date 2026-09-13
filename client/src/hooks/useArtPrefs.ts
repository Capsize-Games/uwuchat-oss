import { useState, useCallback } from "react";

// ── Raw localStorage helpers (no JSON encoding) ─────────────────────────

function getStr(key: string, fallback: string): string {
  try {
    const v = localStorage.getItem(key);
    return v !== null ? v : fallback;
  } catch {
    return fallback;
  }
}

function setStr(key: string, val: string): void {
  try {
    localStorage.setItem(key, val);
  } catch {
    /* quota */
  }
}

// ── useArtPrefs ─────────────────────────────────────────────────────────
// Centralized access to art generation localStorage preferences.
// All art-related localStorage reads/writes MUST go through this hook.

export function useArtPrefs() {
  const [artModel, setArtModelState] = useState(() =>
    getStr("airunner_art_model", ""),
  );
  const [artVersion, setArtVersionState] = useState(() =>
    getStr("airunner_art_version", ""),
  );
  const [seed, setSeedState] = useState(() =>
    getStr("airunner_seed", ""),
  );
  const [scheduler, setSchedulerState] = useState(() =>
    getStr("airunner_art_scheduler", ""),
  );

  const setArtModel = useCallback(
    (m: string) => {
      setStr("airunner_art_model", m);
      setArtModelState(m);
      window.dispatchEvent(
        new CustomEvent("art-model-changed", { detail: m }),
      );
    },
    [],
  );

  const setArtVersion = useCallback(
    (v: string) => {
      setStr("airunner_art_version", v);
      setArtVersionState(v);
      window.dispatchEvent(
        new CustomEvent("art-version-changed", { detail: v }),
      );
    },
    [],
  );

  const setSeed = useCallback(
    (s: string) => {
      setStr("airunner_seed", s);
      setSeedState(s);
    },
    [],
  );

  const setScheduler = useCallback(
    (s: string) => {
      setStr("airunner_art_scheduler", s);
      setSchedulerState(s);
      window.dispatchEvent(
        new CustomEvent("art-scheduler-changed", { detail: s }),
      );
    },
    [],
  );

  return {
    artModel,
    setArtModel,
    artVersion,
    setArtVersion,
    seed,
    setSeed,
    scheduler,
    setScheduler,
  };
}
