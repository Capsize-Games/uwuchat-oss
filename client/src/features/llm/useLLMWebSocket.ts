import { useState, useRef, useCallback, useEffect } from "react";
import type { Message, StreamChunk } from "../../types/api";
import { handleWsMessage } from "./wsMessageHandler";

// ---------------------------------------------------------------------------
// WS URL resolver
// ---------------------------------------------------------------------------

import { wsHost } from "../../api/client-base";
import { getRequestHeaders } from "virtual:extensions";

function wsUrl(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const base = `${proto}://${wsHost()}/api/v1/llm/stream`;
  // WS upgrades can't set custom headers, so the auth token (used to
  // resolve the caller's tenant on the server) must travel in the query
  // string. Without it the server falls back to the anonymous schema and
  // every generated conversation/message is persisted to `tenant_anonymous`
  // instead of the signed-in account's schema. See ws_tenant.py.
  const authHeader = getRequestHeaders()["Authorization"];
  const token = authHeader?.startsWith("Bearer ") ? authHeader.slice(7) : null;
  let url = token ? `${base}?token=${encodeURIComponent(token)}` : base;
  // Pass the last active conversation_id so the server can restore the
  // stored kaomoji immediately on connect (before the first message).
  try {
    const raw = localStorage.getItem("airunner_conversation_id");
    if (raw !== null) {
      const cid = JSON.parse(raw);
      if (cid != null) {
        url += `${url.includes("?") ? "&" : "?"}conversation_id=${cid}`;
      }
    }
  } catch { /* ignore */ }
  return url;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface LLMOptions {
  model?: string;
  temperature?: number;
  max_tokens?: number;
  conversation_id?: number;
  chatbot_id?: number;
  active_document_ids?: number[];
}

/** One completed tool invocation captured during a streamed turn. */
export interface ToolCallRecord {
  tool_id: string;
  tool_name: string;
  status: "starting" | "completed" | "error";
  details?: string | null;
  query?: string;
  /** Character offset in the narration where the tool ran — used for
   *  inline widget placement.  Stamped client-side from the stream
   *  frame order, or server-side for reloaded threads. */
  position?: number;
}

export interface ToolStatusEvent {
  tool_id: string;
  tool_name: string;
  status: "starting" | "completed" | "error";
  details?: string | null;
  query?: string;
  position?: number;
}

export function useLLMWebSocket() {
  const [streaming, setStreaming] = useState(false);
  const [streamBuffer, setStreamBuffer] = useState("");
  const [thinkingBuffer, setThinkingBuffer] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTools, setActiveTools] = useState<ToolStatusEvent[]>([]);
  /** Completed/error tool results accumulated during the current stream,
   *  reset on each send().  Attached to the assistant message on finalize. */
  const [toolEvents, setToolEvents] = useState<ToolCallRecord[]>([]);
  const [mood, setMoodState] = useState("neutral");
  const [moodEmoji, setMoodEmoji] = useState("😐");
  const [moodKaomoji, setMoodKaomoji] = useState("(｡◕ᴗ◕｡)");

  const setMood = useCallback((m: string, e: string, k: string) => {
    setMoodState(m);
    setMoodEmoji(e);
    setMoodKaomoji(k);
  }, []);

  const wsRef = useRef<WebSocket | null>(null);
  const mountedRef = useRef(true);
  // Cumulative visible-narration length for the current stream — used
  // to stamp tool_status frames with their inline narration position.
  // Reset on each send().
  const narrationLengthRef = useRef({ length: 0 });
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  // Incremented each time we start a fresh connection so stale
  // callbacks (from orphaned sockets during StrictMode) are ignored.
  const connGenRef = useRef(0);
  const retryCountRef = useRef(0);
  const MAX_RETRIES = 10;

  // Messages queued while WS is connecting
  const sendQueueRef = useRef<Record<string, unknown>[]>([]);

  // Callbacks set per-stream (not per-hook-lifetime) so we can read
  // the latest values without re-creating the WS connection.
  const onChunkRef = useRef<
    ((chunk: StreamChunk) => void) | null
  >(null);
  const onDoneRef = useRef<(() => void) | null>(null);
  const onErrorRef = useRef<((msg: string) => void) | null>(null);

  const sendMessage = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    } else if (wsRef.current?.readyState === WebSocket.CONNECTING) {
      sendQueueRef.current.push(msg);
    }
  }, []);

  // Flush queued messages when the socket opens
  const flushQueue = useCallback(() => {
    const q = sendQueueRef.current;
    sendQueueRef.current = [];
    for (const msg of q) {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify(msg));
      }
    }
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    // Don't disrupt an in-flight connection.
    if (wsRef.current &&
        (wsRef.current.readyState === WebSocket.OPEN ||
         wsRef.current.readyState === WebSocket.CONNECTING)) {
      return;
    }
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    const gen = ++connGenRef.current;

    try {
      const socket = new WebSocket(wsUrl());
      wsRef.current = socket;

      socket.onopen = () => {
        if (gen !== connGenRef.current) return; // stale
        retryCountRef.current = 0; // reset backoff on successful connect
        flushQueue();
      };

      socket.onmessage = (event) => {
        if (gen !== connGenRef.current) return; // stale
        handleWsMessage(
          event.data as string,
          {
            onChunk: onChunkRef.current,
            onDone: onDoneRef.current,
            onError: onErrorRef.current,
            setError,
            setStreaming,
            setStreamBuffer,
            setThinkingBuffer,
            setIsThinking,
            setActiveTools,
            setMood,
            onToolStatus: (ev: ToolStatusEvent) => {
              if (ev.status === "completed" || ev.status === "error") {
                setToolEvents((prev) => [
                  ...prev,
                  {
                    tool_id: ev.tool_id,
                    tool_name: ev.tool_name,
                    status: ev.status,
                    details: ev.details,
                    ...(ev.query !== undefined ? { query: ev.query } : {}),
                    ...(ev.position !== undefined
                      ? { position: ev.position }
                      : {}),
                  },
                ]);
              }
            },
            onStreamReset: () => {
              setToolEvents([]);
              setActiveTools([]);
            },
          },
          narrationLengthRef.current,
        );
      };

      socket.onclose = (event) => {
        if (gen !== connGenRef.current) return; // stale
        wsRef.current = null;
        if (mountedRef.current && !event.wasClean) {
          if (retryCountRef.current >= MAX_RETRIES) {
            setError("Connection lost — please refresh the page");
            return;
          }
          const backoffMs = Math.min(
            1000 * Math.pow(2, retryCountRef.current) + Math.random() * 500,
            30000,
          );
          retryCountRef.current++;
          reconnectTimerRef.current = setTimeout(connect, backoffMs);
        }
      };

      socket.onerror = () => {
        if (gen !== connGenRef.current) return; // stale
        socket.close();
      };
    } catch {
      if (mountedRef.current) {
        if (retryCountRef.current >= MAX_RETRIES) {
          setError("Connection lost — please refresh the page");
          return;
        }
        const backoffMs = Math.min(
          1000 * Math.pow(2, retryCountRef.current) + Math.random() * 500,
          30000,
        );
        retryCountRef.current++;
        reconnectTimerRef.current = setTimeout(connect, backoffMs);
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    // Connect eagerly so the server can restore the stored kaomoji
    // immediately (before the first user message).
    connect();
    return () => {
      mountedRef.current = false;
      // Bump gen so any orphaned socket callbacks are ignored
      connGenRef.current++;
      if (wsRef.current) {
        // Orphan a CONNECTING socket instead of force-closing it
        // to avoid "WebSocket is closed before the connection is
        // established" errors (e.g. React StrictMode double-mount).
        if (wsRef.current.readyState !== WebSocket.CONNECTING) {
          wsRef.current.close();
        }
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.onmessage = null;
        wsRef.current = null;
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };
  }, [connect]);


  const send = useCallback(
    (
      messages: Message[],
      options?: LLMOptions,
    ): Promise<StreamChunk[]> => {
      return new Promise((resolve, reject) => {
        const chunks: StreamChunk[] = [];

        onChunkRef.current = (chunk: StreamChunk) => {
          chunks.push(chunk);
        };

        onDoneRef.current = () => {
          onChunkRef.current = null;
          onDoneRef.current = null;
          onErrorRef.current = null;
          resolve(chunks);
        };

        onErrorRef.current = (msg: string) => {
          onChunkRef.current = null;
          onDoneRef.current = null;
          onErrorRef.current = null;
          reject(new Error(msg));
        };

        setStreaming(true);
        setStreamBuffer("");
        setThinkingBuffer("");
        setIsThinking(false);
        setActiveTools([]);
        setToolEvents([]);
        narrationLengthRef.current = { length: 0 };
        setError(null);

        // Lazily connect if not already connected
        connect();

        const userLocalTime = new Date().toLocaleString("en-US", {
          weekday: "short",
          month: "short",
          day: "numeric",
          year: "numeric",
          hour: "numeric",
          minute: "2-digit",
          timeZoneName: "short",
        });
        sendMessage({
          type: "chat",
          messages: messages.map((m) => ({
            role: m.role,
            content: m.content,
          })),
          model: options?.model,
          temperature: options?.temperature ?? 0.7,
          max_tokens: options?.max_tokens,
          conversation_id: options?.conversation_id,
          chatbot_id: options?.chatbot_id,
          active_document_ids: options?.active_document_ids,
          user_local_time: userLocalTime,
        });
      });
    },
    [sendMessage, connect],
  );

  const cancel = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "cancel" }));
    }
    setStreaming(false);
    setStreamBuffer("");
    setThinkingBuffer("");
    setIsThinking(false);
    setActiveTools([]);
    onChunkRef.current = null;
    onDoneRef.current = null;
    onErrorRef.current = null;
  }, []);

  const restoreMood = useCallback((conversationId: number) => {
    sendMessage({
      type: "restore_mood",
      conversation_id: conversationId,
    });
  }, [sendMessage]);

  return {
    streaming,
    streamBuffer,
    thinkingBuffer,
    isThinking,
    activeTools,
    toolEvents,
    mood,
    moodEmoji,
    moodKaomoji,
    setMood,
    restoreMood,
    error,
    send,
    cancel,
    setError,
  };
}
