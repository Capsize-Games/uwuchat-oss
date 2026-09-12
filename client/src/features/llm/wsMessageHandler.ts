import type { StreamChunk } from "../../types/api";
import type { ToolStatusEvent } from "./useLLMWebSocket";

export interface WsMessageCallbacks {
  onChunk: ((chunk: StreamChunk) => void) | null;
  onDone: (() => void) | null;
  onError: ((msg: string) => void) | null;
  onQuotaExceeded: ((msg: string) => void) | null;
  /** Called for each tool_status frame with a terminal status. */
  onToolStatus?: (ev: ToolStatusEvent) => void;
  /** Called when the server discards streamed content (stream_reset). */
  onStreamReset?: () => void;
  setError: (msg: string) => void;
  setStreaming: (v: boolean) => void;
  setStreamBuffer: (fn: (prev: string) => string) => void;
  setThinkingBuffer: (fn: (prev: string) => string) => void;
  setIsThinking: (v: boolean) => void;
  setActiveTools: (fn: (prev: ToolStatusEvent[]) => ToolStatusEvent[]) => void;
  setMood: (mood: string, emoji: string, kaomoji: string) => void;
}

/** Track the cumulative visible-narration character length so tool
 *  status frames can be stamped with the narration position at which
 *  they arrive — enabling inline widget placement during streaming. */
export interface NarrationPositionTracker {
  length: number;
}

export function handleWsMessage(
  raw: string,
  cbs: WsMessageCallbacks,
  narration?: NarrationPositionTracker,
): void {
  let data: { type?: string; content?: string; done?: boolean; error?: string; mood?: string; emoji?: string; kaomoji?: string; call_chain_id?: string; status?: string };
  try {
    data = JSON.parse(raw) as typeof data;
  } catch {
    return;
  }

  // Log all incoming message types to verify mood messages arrive
  if (data.type && data.type !== "chunk") {
    console.debug("[wsMessageHandler] received type:", data.type, data);
  }

  if (data.type === "mood") {
    cbs.setMood(data.mood ?? "neutral", data.emoji ?? "😐", data.kaomoji ?? "(｡◕ᴗ◕｡)");
    return;
  }

  if (data.type === "social") {
    const socialData = data as Record<string, unknown>;
    window.dispatchEvent(
      new CustomEvent("uwuchat:block-changed", {
        detail: { chatbotId: socialData.chatbot_id as number | undefined },
      }),
    );
    return;
  }

  if (data.type === "deceased") {
    const d = data as Record<string, unknown>;
    window.dispatchEvent(
      new CustomEvent("uwuchat:chatbot-deceased", {
        detail: { chatbotId: d.chatbot_id as number | undefined },
      }),
    );
    return;
  }

  if (data.type === "stream_reset") {
    cbs.setStreamBuffer(() => "");
    cbs.setThinkingBuffer(() => "");
    cbs.setIsThinking(false);
    // The narration restarted from scratch — reset the position tracker
    // so future tool frames are stamped relative to the new narration,
    // and clear buffered tool events whose positions no longer apply.
    if (narration) {
      narration.length = 0;
    }
    cbs.onStreamReset?.();
    return;
  }

  if (data.type === "error") {
    const msg = data.error ?? data.content ?? "LLM error";
    cbs.setError(msg);
    cbs.onError?.(msg);
    cbs.setStreaming(false);
    cbs.onDone?.();
    return;
  }

  if (data.type === "quota_exceeded") {
    const msg = data.message ?? "You've reached your message limit.";
    cbs.setError(msg);
    cbs.onQuotaExceeded?.(msg);
    cbs.setStreaming(false);
    cbs.onDone?.();
    return;
  }

  if (data.type === "tool_status") {
    const ev = data as unknown as ToolStatusEvent;
    // Stamp the narration position at which this tool frame arrived so
    // the widget can be placed inline (not stacked at the end).
    if (narration) {
      ev.position = narration.length;
    }
    cbs.setActiveTools((prev) => {
      const filtered = prev.filter((t) => t.tool_id !== ev.tool_id);
      if (ev.status === "completed" || ev.status === "error") return filtered;
      return [...filtered, ev];
    });
    if (ev.status === "completed" || ev.status === "error") {
      cbs.onToolStatus?.(ev);
    }
    return;
  }

  if (data.type === "thinking") {
    cbs.setThinkingBuffer((prev) => prev + (data.content ?? ""));
    cbs.setIsThinking(data.status === "started");
    const chunk: StreamChunk = {
      token: data.content ?? "",
      message_type: "thinking",
      done: data.done ?? false,
    };
    cbs.onChunk?.(chunk);
    return;
  }

  const content = data.content ?? "";
  // Strip tool-call syntax like update_mood(...), block_user(...),
  // go_offline(...) from the visible stream so the raw invocation text
  // never appears as a chat message.  Do NOT trim — LLM tokenizers
  // prefix tokens with spaces for word boundaries, and .trim() would
  // strip those spaces, producing smashed-together text.
  const cleaned = content.replace(
    /\b(?:update_mood|block_user|go_offline)\s*\([^)]*\)/g,
    "",
  );
  cbs.setStreamBuffer((prev) => prev + cleaned);
  // Advance the narration-position tracker so tool frames arriving after
  // this chunk get stamped with the correct inline offset.
  if (narration && cleaned) {
    narration.length += cleaned.length;
  }
  const chunk: StreamChunk = {
    token: cleaned,
    done: data.done ?? false,
    call_chain_id: data.done ? (data.call_chain_id ?? undefined) : undefined,
  };
  cbs.onChunk?.(chunk);

  if (data.done) {
    cbs.onDone?.();
    cbs.setStreaming(false);
  }
}
