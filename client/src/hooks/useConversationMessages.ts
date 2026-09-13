import { useState, useCallback, useRef } from "react";
import type { Message, ToolUsage } from "../types/api";
import { loadMessagesDB, saveMessagesDB } from "./messagesDB";

// ── useConversationMessages ───────────────────────────────────────────────────
// Two-tier: IndexedDB cache for immediate display, server for the source of
// truth.  Cached messages are shown immediately on mount so the chat is never
// empty on reload while waiting for the server round-trip.

export function useConversationMessages() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [currentMood, setCurrentMood] = useState<{
    mood?: string;
    emoji?: string;
    kaomoji?: string;
  } | null>(null);
  const pendingLoadId = useRef<number | null>(null);

  const cancelLoad = useCallback(() => {
    pendingLoadId.current = null;
    setLoading(false);
  }, []);

  const load = useCallback(async (conversationId: number) => {
    pendingLoadId.current = conversationId;
    setLoading(true);

    // Show cached messages immediately so the chat is never blank on
    // reload while the server round-trip completes.
    let cacheHit = false;
    loadMessagesDB(conversationId).then((cached) => {
      if (cached && pendingLoadId.current === conversationId) {
        setMessages(cached.messages);
        if (cached.mood?.mood && cached.mood.mood !== "neutral") {
          setCurrentMood(cached.mood);
        }
        cacheHit = true;
      }
    });

    try {
      const { loadConversation } = await import("../api/client");
      const session = await loadConversation(conversationId);
      const rawMsgs = session.messages ?? [];

      if (pendingLoadId.current !== conversationId) return;

      const mapped: Message[] = rawMsgs.map(
        (raw: Record<string, unknown>) => {
          let content = String(raw.content ?? "");
          if (raw.is_bot && content.toLowerCase().startsWith("assistant ")) {
            content = content.slice(10);
          }
          const tc =
            String(raw.thinking_content ?? "") ||
            String(raw.pre_tool_thinking ?? "");
          const toolUsage = Array.isArray(raw.tool_usage)
            ? (raw.tool_usage as ToolUsage[])
            : undefined;
          return {
            role: (raw.is_bot ? "assistant" : "user") as Message["role"],
            content,
            thinking_content: tc || undefined,
            created_at: raw.created_at ? String(raw.created_at) : undefined,
            tool_usage: toolUsage,
          };
        },
      );

      const mood = session.current_mood;
      const resolvedMood =
        mood?.mood && mood.mood !== "neutral" ? mood : null;

      // Extract the most recent server timestamp for newer-wins
      // conflict resolution in the IndexedDB cache layer.
      const newestServerAt = mapped.reduce<string | undefined>(
        (best, m) => {
          if (!m.created_at) return best;
          if (!best || m.created_at > best) return m.created_at;
          return best;
        },
        undefined,
      );

      // Only overwrite cached messages if the server returned data or
      // the cache was never populated — otherwise keep the cached set
      // visible (server may be unreachable).
      if (rawMsgs.length > 0 || !cacheHit) {
        setMessages(mapped);
        setCurrentMood(resolvedMood);
        // Mirror to IndexedDB so messages survive a reload even when
        // the server is temporarily unreachable.
        saveMessagesDB(
          conversationId, mapped, resolvedMood, newestServerAt,
        ).catch(() => {});
      }
    } catch {
      /* network unavailable — keep cached messages if any */
    } finally {
      if (pendingLoadId.current === conversationId) setLoading(false);
    }
  }, []);

  const appendMessage = useCallback(async (
    conversationId: number,
    message: Message,
    _index: number,
  ) => {
    setMessages((prev) => {
      const next = [...prev, message];
      // Keep the cache in sync so the last message isn't lost on reload.
      saveMessagesDB(conversationId, next, null).catch(() => {});
      return next;
    });
  }, []);

  const deleteMessagesAfter = useCallback(
    async (conversationId: number, index: number) => {
      setMessages((prev) => {
        const next = prev.slice(0, index);
        saveMessagesDB(conversationId, next, null).catch(() => {});
        return next;
      });
    },
    [],
  );

  const clear = useCallback(() => setMessages([]), []);

  return {
    messages,
    loading,
    currentMood,
    setMessages,
    load,
    cancelLoad,
    appendMessage,
    deleteMessagesAfter,
    clear,
  };
}
