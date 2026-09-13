import { useState, useCallback, useRef } from "react";
import type { MutableRefObject, Dispatch, SetStateAction } from "react";
import type { Message } from "../types/api";
import type { ActiveDoc } from "../components/chat/types";
import type { useLLMWebSocket } from "@/features/llm/useLLMWebSocket";
import { useAuth } from "./useAuth";
import { getImmersion } from "./useImmersion";
import { normalizeStreamedSpacing } from "@/utils/normalizeStreamedSpacing";

interface UseChatInferenceParams {
  messages: Message[];
  setMessages: Dispatch<SetStateAction<Message[]>>;
  appendMessage: (msg: Message) => void;
  cancelLoad: () => void;
  chatbotId: number | null;
  onSelectChatbot?: (id: number | null) => void;
  conversationIdRef: MutableRefObject<number | null>;
  currentSessionIdRef: MutableRefObject<number | null>;
  modelPathRef: MutableRefObject<string>;
  llm: ReturnType<typeof useLLMWebSocket>;
  activeDocs: ActiveDoc[];
  /** Called when the "is typing…" indicator should appear. */
  onShowTyping?: () => void;
  /** Called when the "is typing…" indicator should disappear. */
  onHideTyping?: () => void;
  /** Called after each successful bot reply is appended. */
  onBotReply?: () => void;
  /** Callback to resolve the session for a given chatbot id. */
  resolveSession?: (
    chatbotId: number,
  ) => Promise<{ conversation_id: number | null; session_id: number | null }>;
}

/** Typical adult reading speeds in words per minute (used for the
 *  pre-typing "reading" delay).  A random value from this range is
 *  picked per-message so it varies naturally. */
const MIN_WPM = 150;
const MAX_WPM = 250;

/** Simulate the chatbot "reading" the user's message before starting
 *  to type.  Based on word count ÷ reading speed plus a random
 *  "thinking" pause so even single-word messages feel natural. */
function readingDelayMs(text: string): number {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  if (words === 0) return 0;
  const wpm = MIN_WPM + Math.random() * (MAX_WPM - MIN_WPM);
  const readTime = (words / wpm) * 60 * 1000;
  // Random thinking pause (600–2000ms) so short messages still have
  // a natural delay before the typing indicator appears.
  const thinkTime = 600 + Math.random() * 1400;
  return Math.min(5000, Math.max(300, readTime + thinkTime));
}

export function useChatInference({
  messages,
  setMessages,
  appendMessage,
  cancelLoad,
  chatbotId,
  onSelectChatbot,
  conversationIdRef,
  currentSessionIdRef,
  modelPathRef,
  llm,
  activeDocs,
  onShowTyping,
  onHideTyping,
  onBotReply,
  resolveSession,
}: UseChatInferenceParams) {
  const { accessToken } = useAuth();
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Holds the full response text after the stream completes so the
  // typewriter reveal can animate toward it even after streamBuffer
  // is cleared by wsMessageHandler on done.
  const pendingResponseRef = useRef<string>("");
  const [streamingReplyReady, setStreamingReplyReady] = useState(false);

  const _pendingThinkingRef = useRef("");
  const _pendingSidRef = useRef<number | null>(null);
  const _pendingCallChainRef = useRef<string | undefined>(undefined);

  const finalizeStreamingReply = useCallback(() => {
    const fullResponse = pendingResponseRef.current;
    if (!fullResponse) return;
    pendingResponseRef.current = "";
    setStreamingReplyReady(false);
    onHideTyping?.();
    appendMessage({
      role: "assistant",
      content: fullResponse,
      thinking_content: _pendingThinkingRef.current || undefined,
      session_id: _pendingSidRef.current ?? undefined,
      call_chain_id: _pendingCallChainRef.current,
      bot_mood: llm.mood,
      bot_mood_emoji: llm.moodEmoji,
      bot_mood_kaomoji: llm.moodKaomoji,
      tool_events: llm.toolEvents,
    });
    if (onBotReply) onBotReply();
  }, [appendMessage, llm, onBotReply, onHideTyping]);

  const doInference = useCallback(
    async (msgs: Message[], userText: string) => {
      setError(null);
      setStreamingReplyReady(false);
      pendingResponseRef.current = "";

      const activeDocIds = activeDocs.map((d) => d.id);
      const sid = currentSessionIdRef.current;
      const sessionMsgs =
        sid != null
          ? msgs.filter(
              (m) => m.session_id == null || m.session_id === sid,
            )
          : msgs;

      const immersion = getImmersion();

      // ── Phase 1: reading delay before typing indicator appears ──────
      if (immersion === "full") {
        const readDelay = readingDelayMs(userText);
        if (readDelay > 0) {
          await new Promise((r) => setTimeout(r, readDelay));
        }

        // Show the "is typing…" indicator.
        onShowTyping?.();
      }

      // ── Request ─────────────────────────────────────────────────────
      let fullResponse = "";
      let thinking = "";
      let callChainId: string | undefined;
      try {
        const chunks = await llm.send(sessionMsgs, {
          model: modelPathRef.current,
          conversation_id: conversationIdRef.current ?? undefined,
          chatbot_id: chatbotId ?? undefined,
          active_document_ids:
            activeDocIds.length > 0 ? activeDocIds : undefined,
        });

        const thinkingChunks: string[] = [];
        for (const chunk of chunks) {
          if (chunk.message_type === "thinking") {
            const token = chunk.token ?? "";
            if (token) thinkingChunks.push(token);
          } else if (chunk.token) {
            fullResponse += chunk.token;
          }
          if (chunk.done && chunk.call_chain_id) {
            callChainId = chunk.call_chain_id;
          }
        }
        // Repair tokenizer word-boundary artifacts (digit gaps like
        // "1 4 9" → "149", missing space before a word after a digit
        // run like "149and" → "149 and") before the reply is stored
        // or displayed.
        fullResponse = normalizeStreamedSpacing(fullResponse);
        thinking = thinkingChunks.join("").trim();
      } catch (err: unknown) {
        onHideTyping?.();
        const msg = err instanceof Error ? err.message : "Stream failed";
        setError(msg);
        // Remove the optimistically-appended user message since
        // the reply never actually happened.
        setMessages((prev) => {
          // Find the last user message (the one we just appended)
          // and remove it, consistent with Task 2 server-side rollback.
          for (let i = prev.length - 1; i >= 0; i--) {
            if (prev[i].role === "user") {
              return prev.slice(0, i);
            }
          }
          return prev;
        });
        // Append a transient system-role message so the error is
        // visible inline where the reply would have appeared.
        appendMessage({
          role: "system",
          content: msg,
          session_id: sid,
        });
        return;
      }

      // Defer appendMessage so the typewriter reveal can animate the
      // response into view at a natural pace.  ChatView calls
      // finalizeStreamingReply once the reveal catches up.
      if (fullResponse) {
        pendingResponseRef.current = fullResponse;
        _pendingThinkingRef.current = thinking;
        _pendingSidRef.current = sid;
        _pendingCallChainRef.current = callChainId;
        setStreamingReplyReady(true);
      } else {
        // Blank response — finalize immediately.
        onHideTyping?.();
        if (onBotReply) onBotReply();
      }
    },
    [
      activeDocs,
      llm,
      appendMessage,
      setMessages,
      onBotReply,
      conversationIdRef,
      currentSessionIdRef,
      modelPathRef,
      onShowTyping,
      onHideTyping,
    ],
  );

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || llm.streaming) return;
    setInput("");

    // Check quota client-side before sending to avoid
    // showing the user message if they're at their limit.
    try {
      if (accessToken) {
        const res = await fetch("/api/v1/usage/quota", {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (res.ok) {
          const q = await res.json();
          const overLimit =
            q.turns_cap && q.turns_used >= q.turns_cap;
          const expired =
            q.period_days_remaining != null &&
            q.period_days_remaining < 0;
          if (overLimit || expired) {
            setError(
              expired
                ? "Your subscription has expired. Upgrade to continue messaging."
                : "You've reached your message limit for this period.",
            );
            return;
          }
        }
      }
    } catch {
      // Proceed — server-side check is the final authority.
    }

    // Ensure we have an active session/conversation for the current chatbot.
    if (conversationIdRef.current === null && chatbotId !== null) {
      try {
        const resolved = resolveSession
          ? await resolveSession(chatbotId)
          : await (await import("../api/chat")).getUwuSession(chatbotId);
        if (resolved.conversation_id) {
          conversationIdRef.current = resolved.conversation_id;
          currentSessionIdRef.current = resolved.session_id;
        }
      } catch {
        // Proceed; messages stay local if session fetch fails.
      }
    }

    const sid = currentSessionIdRef.current;
    const userMsg: Message = {
      role: "user",
      content: text,
      session_id: sid,
    };

    appendMessage(userMsg);
    await doInference([...messages, userMsg], text);
  }, [
    input,
    messages,
    llm.streaming,
    chatbotId,
    appendMessage,
    doInference,
    conversationIdRef,
    currentSessionIdRef,
    modelPathRef,
  ]);

  const sendMessage = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || llm.streaming) return;
    if (conversationIdRef.current === null && chatbotId !== null) {
      try {
        const resolved = resolveSession
          ? await resolveSession(chatbotId)
          : await (await import("../api/chat")).getUwuSession(chatbotId);
        if (resolved.conversation_id) {
          conversationIdRef.current = resolved.conversation_id;
          currentSessionIdRef.current = resolved.session_id;
        }
      } catch {}
    }
    const sid = currentSessionIdRef.current;
    const userMsg: Message = { role: "user", content: trimmed, session_id: sid };
    appendMessage(userMsg);
    await doInference([...messages, userMsg], trimmed);
  }, [llm.streaming, chatbotId, appendMessage, doInference, messages, conversationIdRef, currentSessionIdRef, accessToken]);

  const handleCancel = useCallback(() => llm.cancel(), [llm]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (!llm.streaming) handleSend();
      }
    },
    [handleSend, llm.streaming],
  );

  return {
    input,
    setInput,
    error,
    setError,
    doInference,
    handleSend,
    sendMessage,
    handleCancel,
    handleKeyDown,
    streamingReplyReady,
    finalizeStreamingReply,
  };
}
