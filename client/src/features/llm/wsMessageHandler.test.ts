import { describe, it, expect, vi } from "vitest";
import { handleWsMessage } from "./wsMessageHandler";

function makeCbs() {
  return {
    onChunk: vi.fn(),
    onDone: vi.fn(),
    onError: vi.fn(),
    onQuotaExceeded: vi.fn(),
    onToolStatus: vi.fn(),
    setError: vi.fn(),
    setStreaming: vi.fn(),
    setStreamBuffer: vi.fn(),
    setThinkingBuffer: vi.fn(),
    setIsThinking: vi.fn(),
    setActiveTools: vi.fn(),
    setMood: vi.fn(),
  };
}

describe("wsMessageHandler — thinking messages", () => {
  it("sets isThinking true on status: started with empty content", () => {
    const cbs = makeCbs();
    handleWsMessage(
      JSON.stringify({ type: "thinking", status: "started", content: "" }),
      cbs,
    );
    expect(cbs.setIsThinking).toHaveBeenCalledWith(true);
    expect(cbs.setThinkingBuffer).toHaveBeenCalled();
  });

  it("sets isThinking false on status: completed", () => {
    const cbs = makeCbs();
    handleWsMessage(
      JSON.stringify({ type: "thinking", status: "completed", content: "" }),
      cbs,
    );
    expect(cbs.setIsThinking).toHaveBeenCalledWith(false);
  });

  it("accumulates content in thinkingBuffer while setting isThinking", () => {
    const cbs = makeCbs();
    handleWsMessage(
      JSON.stringify({ type: "thinking", status: "streaming", content: "some reasoning" }),
      cbs,
    );
    expect(cbs.setIsThinking).toHaveBeenCalledWith(false);
    expect(cbs.setThinkingBuffer).toHaveBeenCalled();
    const setFn = cbs.setThinkingBuffer.mock.calls[0][0] as (
      prev: string,
    ) => string;
    expect(setFn("")).toBe("some reasoning");
  });

  it("resets isThinking to false on stream_reset", () => {
    const cbs = makeCbs();
    handleWsMessage(JSON.stringify({ type: "stream_reset" }), cbs);
    expect(cbs.setIsThinking).toHaveBeenCalledWith(false);
    expect(cbs.setThinkingBuffer).toHaveBeenCalled();
  });

  it("does not clobber thinkingBuffer text-accumulation behavior", () => {
    const cbs = makeCbs();
    handleWsMessage(
      JSON.stringify({ type: "thinking", status: "streaming", content: "Hello" }),
      cbs,
    );
    handleWsMessage(
      JSON.stringify({ type: "thinking", status: "streaming", content: " world" }),
      cbs,
    );
    handleWsMessage(
      JSON.stringify({ type: "thinking", status: "completed", content: "" }),
      cbs,
    );
    let buffer = "";
    for (const call of cbs.setThinkingBuffer.mock.calls) {
      buffer = (call[0] as (prev: string) => string)(buffer);
    }
    expect(buffer).toBe("Hello world");
  });

  it("sets isThinking false for standalone thinking message with no status", () => {
    const cbs = makeCbs();
    handleWsMessage(
      JSON.stringify({ type: "thinking", content: "no status field" }),
      cbs,
    );
    expect(cbs.setIsThinking).toHaveBeenCalledWith(false);
  });
});

describe("wsMessageHandler — mood / social / deceased", () => {
  it("updates mood on a mood message", () => {
    const cbs = makeCbs();
    handleWsMessage(
      JSON.stringify({
        type: "mood",
        mood: "happy",
        emoji: "😊",
        kaomoji: "(＾▽＾)",
      }),
      cbs,
    );
    expect(cbs.setMood).toHaveBeenCalledWith("happy", "😊", "(＾▽＾)");
  });

  it("defaults mood fields when missing", () => {
    const cbs = makeCbs();
    handleWsMessage(JSON.stringify({ type: "mood" }), cbs);
    expect(cbs.setMood).toHaveBeenCalledWith("neutral", "😐", "(｡◕ᴗ◕｡)");
  });

  it("dispatches a block-changed event for social messages", () => {
    const cbs = makeCbs();
    const dispatch = vi.fn();
    vi.stubGlobal("window", { dispatchEvent: dispatch });
    handleWsMessage(
      JSON.stringify({ type: "social", chatbot_id: 7 }),
      cbs,
    );
    expect(dispatch).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("dispatches a chatbot-deceased event", () => {
    const cbs = makeCbs();
    const dispatch = vi.fn();
    vi.stubGlobal("window", { dispatchEvent: dispatch });
    handleWsMessage(
      JSON.stringify({ type: "deceased", chatbot_id: 7 }),
      cbs,
    );
    expect(dispatch).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});

describe("wsMessageHandler — error / quota / tool_status / chunk", () => {
  it("handles error messages", () => {
    const cbs = makeCbs();
    handleWsMessage(
      JSON.stringify({ type: "error", error: "boom", content: "fallback" }),
      cbs,
    );
    expect(cbs.setError).toHaveBeenCalledWith("boom");
    expect(cbs.onError).toHaveBeenCalledWith("boom");
    expect(cbs.setStreaming).toHaveBeenCalledWith(false);
    expect(cbs.onDone).toHaveBeenCalled();
  });

  it("handles error with only content", () => {
    const cbs = makeCbs();
    handleWsMessage(JSON.stringify({ type: "error", content: "only" }), cbs);
    expect(cbs.setError).toHaveBeenCalledWith("only");
  });

  it("handles error with neither field", () => {
    const cbs = makeCbs();
    handleWsMessage(JSON.stringify({ type: "error" }), cbs);
    expect(cbs.setError).toHaveBeenCalledWith("LLM error");
  });

  it("handles quota_exceeded", () => {
    const cbs = makeCbs();
    handleWsMessage(
      JSON.stringify({ type: "quota_exceeded", message: "limit" }),
      cbs,
    );
    expect(cbs.setError).toHaveBeenCalledWith("limit");
    expect(cbs.onQuotaExceeded).toHaveBeenCalledWith("limit");
    expect(cbs.onDone).toHaveBeenCalled();
  });

  it("handles quota_exceeded with default message", () => {
    const cbs = makeCbs();
    handleWsMessage(JSON.stringify({ type: "quota_exceeded" }), cbs);
    expect(cbs.setError).toHaveBeenCalledWith(
      "You've reached your message limit.",
    );
  });

  it("adds a starting tool_status to activeTools", () => {
    const cbs = makeCbs();
    cbs.setActiveTools.mockImplementation(
      (fn: (prev: unknown[]) => unknown[]) => fn([]),
    );
    handleWsMessage(
      JSON.stringify({
        type: "tool_status",
        tool_id: "tc-1",
        tool_name: "execute_command",
        status: "starting",
      }),
      cbs,
    );
    const result = cbs.setActiveTools.mock.calls[0][0]([]) as Array<{
      tool_id: string;
      type?: string;
    }>;
    expect(result).toEqual([
      {
        type: "tool_status",
        tool_id: "tc-1",
        tool_name: "execute_command",
        status: "starting",
      },
    ]);
    // Starting status does not forward to onToolStatus.
    expect(cbs.onToolStatus).not.toHaveBeenCalled();
  });

  it("forwards completed tool_status to onToolStatus", () => {
    const cbs = makeCbs();
    handleWsMessage(
      JSON.stringify({
        type: "tool_status",
        tool_id: "tc-1",
        tool_name: "execute_command",
        status: "completed",
        details: "src/\nfile.ts",
      }),
      cbs,
    );
    expect(cbs.onToolStatus).toHaveBeenCalledWith({
      type: "tool_status",
      tool_id: "tc-1",
      tool_name: "execute_command",
      status: "completed",
      details: "src/\nfile.ts",
    });
  });

  it("stamps the narration position when a tracker is provided", () => {
    const cbs = makeCbs();
    const narration = { length: 23 };
    handleWsMessage(
      JSON.stringify({
        type: "tool_status",
        tool_id: "tc-1",
        tool_name: "execute_command",
        status: "completed",
        details: "ok",
      }),
      cbs,
      narration,
    );
    expect(cbs.onToolStatus).toHaveBeenCalledWith(
      expect.objectContaining({ position: 23 }),
    );
  });

  it("advances the narration tracker with streamed content", () => {
    const cbs = makeCbs();
    const narration = { length: 0 };
    handleWsMessage(
      JSON.stringify({ type: "chunk", content: "I'll check the file." }),
      cbs,
      narration,
    );
    handleWsMessage(
      JSON.stringify({
        type: "tool_status",
        tool_id: "tc-1",
        tool_name: "execute_command",
        status: "completed",
        details: "ok",
      }),
      cbs,
      narration,
    );
    // 20 chars of narration streamed before the tool frame arrived.
    expect(narration.length).toBe(20);
    expect(cbs.onToolStatus).toHaveBeenCalledWith(
      expect.objectContaining({ position: 20 }),
    );
  });

  it("forwards error tool_status to onToolStatus", () => {
    const cbs = makeCbs();
    handleWsMessage(
      JSON.stringify({
        type: "tool_status",
        tool_id: "tc-2",
        tool_name: "execute_command",
        status: "error",
        details: "Tool error: All connection attempts failed",
      }),
      cbs,
    );
    expect(cbs.onToolStatus).toHaveBeenCalledWith(
      expect.objectContaining({
        tool_id: "tc-2",
        status: "error",
        details: "Tool error: All connection attempts failed",
      }),
    );
  });

  it("removes a completed tool_status from activeTools", () => {
    const cbs = makeCbs();
    cbs.setActiveTools.mockImplementation(
      (fn: (prev: unknown[]) => unknown[]) =>
        fn([{ tool_id: "tc-1", tool_name: "x", status: "starting" }]),
    );
    handleWsMessage(
      JSON.stringify({
        type: "tool_status",
        tool_id: "tc-1",
        tool_name: "execute_command",
        status: "completed",
      }),
      cbs,
    );
    const result = cbs.setActiveTools.mock.calls[0][0]([
      { tool_id: "tc-1", tool_name: "x", status: "starting" },
    ]) as unknown[];
    expect(result).toEqual([]);
  });

  it("accumulates chunk content in streamBuffer", () => {
    const cbs = makeCbs();
    cbs.setStreamBuffer.mockImplementation(
      (fn: (prev: string) => string) => fn("prev"),
    );
    handleWsMessage(JSON.stringify({ type: "chunk", content: "hi" }), cbs);
    const result = cbs.setStreamBuffer.mock.calls[0][0]("prev");
    expect(result).toBe("prevhi");
    expect(cbs.onChunk).toHaveBeenCalled();
  });

  it("strips tool-call markup from chunk content", () => {
    const cbs = makeCbs();
    cbs.setStreamBuffer.mockImplementation((fn: (prev: string) => string) => fn(""));
    handleWsMessage(
      JSON.stringify({ type: "chunk", content: "update_mood(happy) hello" }),
      cbs,
    );
    const result = cbs.setStreamBuffer.mock.calls[0][0]("");
    expect(result).toBe(" hello");
  });

  it("calls onDone and setStreaming(false) on final chunk", () => {
    const cbs = makeCbs();
    cbs.setStreamBuffer.mockImplementation((fn: (prev: string) => string) => fn(""));
    handleWsMessage(
      JSON.stringify({ type: "chunk", content: "done", done: true, call_chain_id: "c1" }),
      cbs,
    );
    expect(cbs.onDone).toHaveBeenCalled();
    expect(cbs.setStreaming).toHaveBeenCalledWith(false);
    expect(cbs.onChunk).toHaveBeenCalledWith(
      expect.objectContaining({ call_chain_id: "c1", done: true }),
    );
  });

  it("ignores malformed JSON", () => {
    const cbs = makeCbs();
    handleWsMessage("not json", cbs);
    expect(cbs.setStreamBuffer).not.toHaveBeenCalled();
    expect(cbs.onChunk).not.toHaveBeenCalled();
  });
});
