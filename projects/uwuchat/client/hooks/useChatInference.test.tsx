import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import type { Message } from "../../../client/types/api";

// The hook's deps are framework modules; mock them so the hook runs
// against deterministic stubs.
vi.mock("./useAuth", () => ({
  useAuth: () => ({ accessToken: "token-1" }),
}));
vi.mock("./useImmersion", () => ({
  getImmersion: () => "minimal",
}));

import { useChatInference } from "./useChatInference";

function makeLlm() {
  return {
    streaming: false,
    mood: "neutral",
    moodEmoji: "😐",
    moodKaomoji: "(｡◕ᴗ◕｡)",
    send: vi.fn(),
    cancel: vi.fn(),
    error: null,
    toolEvents: [],
  };
}

function makeParams(overrides: Record<string, unknown> = {}) {
  const messages: Message[] = [];
  const setMessages = vi.fn();
  const appendMessage = vi.fn();
  const llm = makeLlm();
  const conversationIdRef = { current: null as number | null };
  const currentSessionIdRef = { current: null as number | null };
  const modelPathRef = { current: "model-x" };
  return {
    messages,
    setMessages,
    appendMessage,
    cancelLoad: vi.fn(),
    chatbotId: 1,
    onSelectChatbot: vi.fn(),
    conversationIdRef,
    currentSessionIdRef,
    modelPathRef,
    llm,
    activeDocs: [],
    onShowTyping: vi.fn(),
    onHideTyping: vi.fn(),
    onBotReply: vi.fn(),
    resolveSession: vi.fn(),
    ...overrides,
  };
}

describe("useChatInference", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("initializes with empty input and no error", () => {
    const { result } = renderHook(() => useChatInference(makeParams()));
    expect(result.current.input).toBe("");
    expect(result.current.error).toBeNull();
    expect(result.current.streamingReplyReady).toBe(false);
  });

  it("setInput updates the input state", () => {
    const { result } = renderHook(() => useChatInference(makeParams()));
    act(() => result.current.setInput("hello"));
    expect(result.current.input).toBe("hello");
  });

  it("handleSend appends the user message and calls doInference", async () => {
    const params = makeParams();
    const chunks = [{ token: "hi", done: true }];
    params.llm.send.mockResolvedValue(chunks);
    params.resolveSession.mockResolvedValue({
      conversation_id: 5,
      session_id: 9,
    });
    const { result } = renderHook(() => useChatInference(params));
    act(() => result.current.setInput("hello"));
    await act(async () => {
      await result.current.handleSend();
    });
    expect(params.appendMessage).toHaveBeenCalledWith(
      expect.objectContaining({ role: "user", content: "hello" }),
    );
    // Session resolved and stored.
    expect(params.conversationIdRef.current).toBe(5);
    expect(params.currentSessionIdRef.current).toBe(9);
  });

  it("handleSend with empty input does nothing", async () => {
    const params = makeParams();
    const { result } = renderHook(() => useChatInference(params));
    await act(async () => {
      await result.current.handleSend();
    });
    expect(params.appendMessage).not.toHaveBeenCalled();
  });

  it("handleSend respects llm.streaming", async () => {
    const params = makeParams();
    params.llm.streaming = true;
    const { result } = renderHook(() => useChatInference(params));
    act(() => result.current.setInput("hello"));
    await act(async () => {
      await result.current.handleSend();
    });
    expect(params.appendMessage).not.toHaveBeenCalled();
  });

  it("handleSend surfaces quota errors", async () => {
    const params = makeParams();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ turns_cap: 10, turns_used: 10 }),
    }));
    const { result } = renderHook(() => useChatInference(params));
    act(() => result.current.setInput("hello"));
    await act(async () => {
      await result.current.handleSend();
    });
    expect(result.current.error).toBe(
      "You've reached your message limit for this period.",
    );
    expect(params.appendMessage).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("handleSend surfaces expired subscription", async () => {
    const params = makeParams();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ period_days_remaining: -1 }),
    }));
    const { result } = renderHook(() => useChatInference(params));
    act(() => result.current.setInput("hello"));
    await act(async () => {
      await result.current.handleSend();
    });
    expect(result.current.error).toBe(
      "Your subscription has expired. Upgrade to continue messaging.",
    );
    vi.unstubAllGlobals();
  });

  it("doInference sets streamingReplyReady with a full response", async () => {
    const params = makeParams();
    params.llm.send.mockResolvedValue([
      { token: "hel", done: false },
      { token: "lo", done: true },
    ]);
    const { result } = renderHook(() => useChatInference(params));
    await act(async () => {
      await result.current.doInference([{ role: "user", content: "x" }], "x");
    });
    expect(result.current.streamingReplyReady).toBe(true);
  });

  it("doInference handles errors by rolling back the user message", async () => {
    const params = makeParams();
    params.llm.send.mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useChatInference(params));
    await act(async () => {
      await result.current.doInference(
        [{ role: "user", content: "x" }],
        "x",
      );
    });
    expect(result.current.error).toBe("boom");
    expect(params.onHideTyping).toHaveBeenCalled();
    // The error system message was appended.
    expect(params.appendMessage).toHaveBeenCalledWith(
      expect.objectContaining({ role: "system", content: "boom" }),
    );
    // The user message was removed via setMessages.
    expect(params.setMessages).toHaveBeenCalled();
  });

  it("doInference with blank response finalizes immediately", async () => {
    const params = makeParams();
    params.llm.send.mockResolvedValue([]);
    const { result } = renderHook(() => useChatInference(params));
    await act(async () => {
      await result.current.doInference([{ role: "user", content: "x" }], "x");
    });
    expect(result.current.streamingReplyReady).toBe(false);
    expect(params.onHideTyping).toHaveBeenCalled();
  });

  it("finalizeStreamingReply appends the assistant message", async () => {
    const params = makeParams();
    params.llm.send.mockResolvedValue([
      { token: "hi", done: true },
    ]);
    const { result } = renderHook(() => useChatInference(params));
    await act(async () => {
      await result.current.doInference([{ role: "user", content: "x" }], "x");
    });
    expect(result.current.streamingReplyReady).toBe(true);
    await act(async () => {
      result.current.finalizeStreamingReply();
    });
    expect(params.appendMessage).toHaveBeenCalledWith(
      expect.objectContaining({ role: "assistant", content: "hi" }),
    );
    expect(result.current.streamingReplyReady).toBe(false);
    expect(params.onBotReply).toHaveBeenCalled();
  });

  it("finalizeStreamingReply attaches tool_events to the message", async () => {
    const params = makeParams();
    params.llm.toolEvents = [
      {
        tool_id: "tc-1",
        tool_name: "execute_command",
        status: "error",
        details: "Tool error: All connection attempts failed",
      },
    ];
    params.llm.send.mockResolvedValue([{ token: "hi", done: true }]);
    const { result } = renderHook(() => useChatInference(params));
    await act(async () => {
      await result.current.doInference([{ role: "user", content: "x" }], "x");
    });
    await act(async () => {
      result.current.finalizeStreamingReply();
    });
    expect(params.appendMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        role: "assistant",
        content: "hi",
        tool_events: params.llm.toolEvents,
      }),
    );
  });

  it("finalizeStreamingReply with no pending response does nothing", () => {
    const params = makeParams();
    const { result } = renderHook(() => useChatInference(params));
    act(() => result.current.finalizeStreamingReply());
    expect(params.appendMessage).not.toHaveBeenCalled();
  });

  it("sendMessage appends and runs inference", async () => {
    const params = makeParams();
    params.llm.send.mockResolvedValue([{ token: "ok", done: true }]);
    const { result } = renderHook(() => useChatInference(params));
    await act(async () => {
      await result.current.sendMessage("  hello  ");
    });
    expect(params.appendMessage).toHaveBeenCalledWith(
      expect.objectContaining({ role: "user", content: "hello" }),
    );
  });

  it("handleCancel calls llm.cancel", () => {
    const params = makeParams();
    const { result } = renderHook(() => useChatInference(params));
    act(() => result.current.handleCancel());
    expect(params.llm.cancel).toHaveBeenCalled();
  });

  it("handleKeyDown Enter without shift sends", async () => {
    const params = makeParams();
    params.llm.send.mockResolvedValue([{ token: "ok", done: true }]);
    const { result } = renderHook(() => useChatInference(params));
    act(() => result.current.setInput("hi"));
    const e = {
      key: "Enter",
      shiftKey: false,
      preventDefault: vi.fn(),
    } as unknown as React.KeyboardEvent<HTMLTextAreaElement>;
    await act(async () => {
      result.current.handleKeyDown(e);
      await Promise.resolve();
    });
    expect(e.preventDefault).toHaveBeenCalled();
  });

  it("handleKeyDown with shift does not send", () => {
    const params = makeParams();
    const { result } = renderHook(() => useChatInference(params));
    const e = {
      key: "Enter",
      shiftKey: true,
      preventDefault: vi.fn(),
    } as unknown as React.KeyboardEvent<HTMLTextAreaElement>;
    act(() => result.current.handleKeyDown(e));
    expect(e.preventDefault).not.toHaveBeenCalled();
  });
});
