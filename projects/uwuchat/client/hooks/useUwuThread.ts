import { useState, useCallback, useRef } from "react";
import type { Message } from "../types/api";

export interface ThreadMood {
  mood: string;
  emoji: string;
  kaomoji: string;
}

export function useUwuThread() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [threadMood, setThreadMood] = useState<ThreadMood | null>(null);
  const pendingChatbotId = useRef<number | null>(null);
  const errorRef = useRef<Error | null>(null);

  const load = useCallback(async (chatbotId: number): Promise<Message[]> => {
    pendingChatbotId.current = chatbotId;
    setLoading(true);
    setError(null);
    errorRef.current = null;

    const MAX_RETRIES = 3;
    const RETRY_DELAY_MS = 2000;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const { loadUwuThread } = await import("../api/chat");
        const resp = await loadUwuThread(chatbotId);
        if (pendingChatbotId.current !== chatbotId) return [];
        const raw = resp.messages ?? [];
        const mapped: Message[] = (raw as Record<string, unknown>[])
          .filter((m) => {
            const r = String(m.role ?? "");
            if (r !== "user" && r !== "assistant") return false;
            if (m.metadata_type === "proactive_trigger") return false;
            return true;
          })
          .map((m) => {
            const content = String(m.content ?? "");
            const tc = String(m.thinking_content ?? "") || String(m.pre_tool_thinking ?? "");
            const role: Message["role"] =
              String(m.role) === "assistant" ? "assistant" : "user";
            return {
              id: m.id != null ? Number(m.id) : undefined,
              role,
              content,
              thinking_content: tc || undefined,
              created_at: m.created_at
                ? String(m.created_at)
                : m.timestamp
                ? String(m.timestamp)
                : undefined,
              session_id: m.session_id != null ? Number(m.session_id) : null,
              session_started_at: m.session_started_at ? String(m.session_started_at) : null,
              call_chain_id: m.call_chain_id ? String(m.call_chain_id) : null,
              bot_mood: m.bot_mood ? String(m.bot_mood) : undefined,
              bot_mood_emoji: m.bot_mood_emoji ? String(m.bot_mood_emoji) : undefined,
              bot_mood_kaomoji: m.bot_mood_kaomoji ? String(m.bot_mood_kaomoji) : undefined,
              tool_events: Array.isArray(m.tool_events)
                ? (m.tool_events as Message["tool_events"])
                : undefined,
              headlesscode_session_id: m.headlesscode_session_id
                ? String(m.headlesscode_session_id)
                : undefined,
              headlesscode_project_name: m.project_name
                ? String(m.project_name)
                : undefined,
              headlesscode_status: m.status
                ? String(m.status)
                : undefined,
              headlesscode_task: m.task_description
                ? String(m.task_description)
                : undefined,
            };
          });
        setMessages(mapped);
        // conv.user_data["current_mood"] reflects async background mood
        // updates that fire after messages are saved — use it first.
        // Fall back to the last per-message mood for older conversations
        // that predate background mood updates.
        const cm = resp.current_mood;
        if (cm?.mood) {
          setThreadMood({
            mood: cm.mood,
            emoji: cm.emoji ?? "😐",
            kaomoji: cm.kaomoji ?? "(｡◕ᴗ◕｡)",
          });
        } else {
          const lastBotMsg = mapped.slice().reverse().find(
            (msg) => msg.role === "assistant" && msg.bot_mood,
          );
          if (lastBotMsg?.bot_mood) {
            setThreadMood({
              mood: lastBotMsg.bot_mood,
              emoji: lastBotMsg.bot_mood_emoji ?? "😐",
              kaomoji: lastBotMsg.bot_mood_kaomoji ?? "(｡◕ᴗ◕｡)",
            });
          } else {
            setThreadMood(null);
          }
        }
        if (pendingChatbotId.current === chatbotId) setLoading(false);
        return mapped;
      } catch (err) {
        if (pendingChatbotId.current !== chatbotId) return [];
        if (attempt < MAX_RETRIES) {
          await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
        } else {
          const e = err instanceof Error ? err : new Error(String(err));
          errorRef.current = e;
          setError(e);
          if (pendingChatbotId.current === chatbotId) setLoading(false);
          return [];
        }
      }
    }

    // Should never reach here — safety net.
    if (pendingChatbotId.current === chatbotId) setLoading(false);
    return [];
  }, []);

  const cancelLoad = useCallback(() => {
    pendingChatbotId.current = null;
    setLoading(false);
    setError(null);
    errorRef.current = null;
  }, []);

  const appendMessage = useCallback((message: Message) => {
    setMessages((prev) => [
      ...prev,
      {
        ...message,
        created_at: message.created_at ?? new Date().toISOString(),
      },
    ]);
  }, []);

  const clear = useCallback(() => setMessages([]), []);

  return { messages, setMessages, loading, error, errorRef, load, cancelLoad, appendMessage, clear, threadMood };
}
