import { useCallback, useEffect, useState } from "react";
import {
  getCodeMode,
  setCodeMode,
  type CodeModeSlug,
} from "../api/codeMode";

interface UseCodeMode {
  /** True when the current conversation has code mode on. */
  enabled: boolean;
  /** Which headlesscode mode is selected (only meaningful when
   *  enabled, or when pending — the mode that will apply once a
   *  conversation resolves). */
  mode: CodeModeSlug;
  /** True when the user has armed code mode for the next conversation
   *  (no conversation resolved yet — "start as code"). */
  pending: boolean;
  loading: boolean;
  /** Select a mode (turns code mode on for that mode), or pass `null`
   *  to turn code mode off. Before a conversation resolves, this just
   *  arms/disarms the "start as code" intent locally. */
  select: (mode: CodeModeSlug | null) => Promise<void>;
  /** Clear the start-as-code intent (called once the first message has
   *  created the conversation). */
  clearPending: () => void;
}

/**
 * Admin-only code-mode + mode-picker state for one conversation.
 *
 * - When *conversationId* is set, reads/writes the conversation's
 *   ``user_data.code_mode`` / ``code_mode_slug`` (see
 *   code_mode_service.py).
 * - When *conversationId* is null (no conversation yet), the hook tracks
 *   a local ``pending``/``mode`` intent so a superuser can arm code mode
 *   (and pick which sub-mode) before the first message creates the
 *   conversation ("start as code").
 *
 * Callers gate visibility on ``user.is_superuser``.
 */
export function useCodeMode(conversationId: number | null): UseCodeMode {
  const [enabled, setEnabled] = useState(false);
  const [mode, setModeState] = useState<CodeModeSlug>("code");
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (conversationId === null) {
      setEnabled(false);
      return;
    }
    let cancelled = false;
    getCodeMode(conversationId)
      .then((res) => {
        if (cancelled) return;
        setEnabled(res.enabled);
        setModeState(res.mode);
      })
      .catch(() => {
        if (!cancelled) setEnabled(false);
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  const select = useCallback(
    async (nextMode: CodeModeSlug | null) => {
      if (loading) return;
      if (conversationId === null) {
        // No conversation yet — arm/disarm the start-as-code intent.
        if (nextMode === null) {
          setPending(false);
        } else {
          setPending(true);
          setModeState(nextMode);
        }
        return;
      }
      setLoading(true);
      try {
        const res =
          nextMode === null
            ? await setCodeMode(conversationId, false)
            : await setCodeMode(conversationId, true, nextMode);
        setEnabled(res.enabled);
        setModeState(res.mode);
      } finally {
        setLoading(false);
      }
    },
    [conversationId, loading],
  );

  const clearPending = useCallback(() => {
    setPending(false);
  }, []);

  return { enabled, mode, pending, loading, select, clearPending };
}
