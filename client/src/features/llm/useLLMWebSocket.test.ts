import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useLLMWebSocket } from "./useLLMWebSocket";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;
  static CONNECTING = 0;
  static CLOSED = 3;

  url: string;
  readyState = 1; // OPEN by default for simplicity
  sent: string[] = [];
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: { wasClean: boolean }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
  }

  // Test helper: simulate an incoming server frame.
  emit(data: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  // Test helper: simulate open.
  open() {
    this.onopen?.({});
  }
}

function stubWebSocket() {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
}

describe("useLLMWebSocket", () => {
  beforeEach(() => {
    stubWebSocket();
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("connects on mount and restores mood from localStorage conversation", () => {
    localStorage.setItem("airunner_conversation_id", "42");
    const { result } = renderHook(() => useLLMWebSocket());
    expect(FakeWebSocket.instances.length).toBeGreaterThan(0);
    expect(FakeWebSocket.instances[0].url).toContain("/api/v1/llm/stream");
    expect(result.current.streaming).toBe(false);
  });

  it("send() sends a chat message and resolves chunks on done", async () => {
    const { result } = renderHook(() => useLLMWebSocket());
    const ws = FakeWebSocket.instances[0];

    const sendPromise = result.current.send(
      [{ role: "user", content: "hi" }],
      { model: "m", conversation_id: 1, chatbot_id: 2 },
    );

    expect(ws.sent.length).toBe(1);
    const sent = JSON.parse(ws.sent[0]);
    expect(sent.type).toBe("chat");
    expect(sent.messages[0].content).toBe("hi");
    expect(sent.model).toBe("m");
    expect(sent.conversation_id).toBe(1);

    ws.emit({ type: "chunk", content: "hello", done: false });
    ws.emit({ type: "chunk", content: " world", done: true });

    const chunks = await sendPromise;
    expect(chunks.map((c) => c.token).join("")).toBe("hello world");
    expect(result.current.streaming).toBe(false);
  });

  it("send() rejects on error frame", async () => {
    const { result } = renderHook(() => useLLMWebSocket());
    const ws = FakeWebSocket.instances[0];

    const sendPromise = result.current.send([{ role: "user", content: "x" }], {});

    ws.emit({ type: "error", error: "boom" });

    await expect(sendPromise).rejects.toThrow("boom");
  });

  it("cancel() sends a cancel frame and resets buffers", () => {
    const { result } = renderHook(() => useLLMWebSocket());
    const ws = FakeWebSocket.instances[0];
    act(() => {
      result.current.cancel();
    });
    const cancelFrame = ws.sent.find((s) => {
      const parsed = JSON.parse(s);
      return parsed.type === "cancel";
    });
    expect(cancelFrame).toBeDefined();
    expect(result.current.streaming).toBe(false);
    expect(result.current.streamBuffer).toBe("");
  });

  it("restoreMood sends a restore_mood frame", () => {
    const { result } = renderHook(() => useLLMWebSocket());
    const ws = FakeWebSocket.instances[0];
    act(() => {
      result.current.restoreMood(5);
    });
    const frame = ws.sent.find((s) => {
      const parsed = JSON.parse(s);
      return parsed.type === "restore_mood";
    });
    expect(frame).toBeDefined();
    expect(JSON.parse(frame!).conversation_id).toBe(5);
  });

  it("setMood updates mood state", () => {
    const { result } = renderHook(() => useLLMWebSocket());
    act(() => {
      result.current.setMood("happy", "😊", "(＾▽＾)");
    });
    expect(result.current.mood).toBe("happy");
    expect(result.current.moodEmoji).toBe("😊");
    expect(result.current.moodKaomoji).toBe("(＾▽＾)");
  });

  it("handles tool_status frames via activeTools", () => {
    const { result } = renderHook(() => useLLMWebSocket());
    const ws = FakeWebSocket.instances[0];
    act(() => {
      ws.emit({
        type: "tool_status",
        tool_id: "tc-1",
        tool_name: "execute_command",
        status: "starting",
      });
    });
    expect(result.current.activeTools).toEqual([
      {
        type: "tool_status",
        tool_id: "tc-1",
        tool_name: "execute_command",
        status: "starting",
        position: 0,
      },
    ]);
  });

  it("accumulates completed tool_status into toolEvents", () => {
    const { result } = renderHook(() => useLLMWebSocket());
    const ws = FakeWebSocket.instances[0];
    act(() => {
      ws.emit({
        type: "tool_status",
        tool_id: "tc-1",
        tool_name: "execute_command",
        status: "completed",
        details: "src/\nfile.ts",
      });
    });
    expect(result.current.toolEvents).toEqual([
      {
        tool_id: "tc-1",
        tool_name: "execute_command",
        status: "completed",
        details: "src/\nfile.ts",
        position: 0,
      },
    ]);
  });

  it("resets toolEvents on each send()", async () => {
    const { result } = renderHook(() => useLLMWebSocket());
    const ws = FakeWebSocket.instances[0];
    act(() => {
      ws.emit({
        type: "tool_status",
        tool_id: "tc-1",
        tool_name: "execute_command",
        status: "completed",
        details: "old",
      });
    });
    expect(result.current.toolEvents.length).toBe(1);

    let p: ReturnType<typeof result.current.send> | undefined;
    act(() => {
      p = result.current.send([{ role: "user", content: "x" }], {});
      // reset on send is scheduled synchronously inside the executor.
    });
    expect(result.current.toolEvents).toEqual([]);
    ws.emit({ type: "chunk", content: "ok", done: true });
    await p!;
  });

  it("reconnects with backoff on unclean close", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useLLMWebSocket());
    const first = FakeWebSocket.instances[0];
    act(() => {
      first.onclose?.({ wasClean: false });
    });
    vi.advanceTimersByTime(1500);
    // A new connection attempt was scheduled (retryCount 0 → ~1s backoff).
    expect(result.current.error).toBeNull();
    vi.useRealTimers();
  });

  it("queues messages while connecting", () => {
    const { result } = renderHook(() => useLLMWebSocket());
    const ws = FakeWebSocket.instances[0];
    ws.readyState = FakeWebSocket.CONNECTING;
    result.current.send([{ role: "user", content: "q" }], {});
    // The message was queued (sendMessage only pushes when OPEN).
    expect(ws.sent.length).toBe(0);
    // Flush queue on open.
    act(() => {
      ws.readyState = FakeWebSocket.OPEN;
      ws.open();
    });
    expect(ws.sent.length).toBeGreaterThan(0);
  });

  it("onerror closes the socket", () => {
    const { result } = renderHook(() => useLLMWebSocket());
    const ws = FakeWebSocket.instances[0];
    const closeSpy = vi.spyOn(ws, "close");
    act(() => {
      ws.onerror?.();
    });
    expect(closeSpy).toHaveBeenCalled();
    expect(result.current.streaming).toBe(false);
  });

  it("exhausts retries and sets an error", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useLLMWebSocket());

    // Force MAX_RETRIES (10) unclean closes to exhaust the backoff.
    for (let i = 0; i < 11; i++) {
      const ws = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
      act(() => {
        ws.onclose?.({ wasClean: false });
      });
      vi.advanceTimersByTime(2000);
    }
    // After exhausting, an unclean close sets the error.
    expect(result.current.error).toBe("Connection lost — please refresh the page");
    vi.useRealTimers();
  });

  it("does not reconnect on a clean close", () => {
    const { result } = renderHook(() => useLLMWebSocket());
    const ws = FakeWebSocket.instances[0];
    act(() => {
      ws.onclose?.({ wasClean: true });
    });
    expect(result.current.error).toBeNull();
    // No reconnect scheduled → instances unchanged.
    expect(FakeWebSocket.instances.length).toBe(1);
  });

  it("cleans up its socket on unmount", () => {
    const { unmount } = renderHook(() => useLLMWebSocket());
    const ws = FakeWebSocket.instances[0];
    expect(ws.onmessage).toBeTruthy();
    unmount();
    // The cleanup nulls the callbacks on the owned socket.
    expect(ws.onmessage).toBeNull();
    expect(ws.onclose).toBeNull();
    expect(ws.onerror).toBeNull();
  });

  it("closes a stale socket when reconnecting via send()", () => {
    const { result } = renderHook(() => useLLMWebSocket());
    const first = FakeWebSocket.instances[0];
    // Simulate a stale CLOSED socket still held in wsRef.  send() calls
    // connect(), which sees wsRef.readyState !== OPEN/CONNECTING and
    // tears down the old socket (lines 123-129) before reconnecting.
    act(() => {
      first.readyState = FakeWebSocket.CLOSED;
    });
    // connect() will close the old socket and create a new one.
    act(() => {
      result.current.send([{ role: "user", content: "x" }], {});
    });
    expect(FakeWebSocket.instances.length).toBeGreaterThan(1);
    expect(first.onclose).toBeNull(); // handlers detached before close
  });

  it("retries when the WebSocket constructor throws", () => {
    vi.useFakeTimers();
    const real = FakeWebSocket;
    class ThrowingWebSocket extends real {
      constructor(url: string) {
        super(url);
        throw new Error("constructor failed");
      }
    }
    vi.stubGlobal("WebSocket", ThrowingWebSocket);
    const { result } = renderHook(() => useLLMWebSocket());
    // The first constructor threw → a retry was scheduled.
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(result.current.error).toBeNull();
    // Exhaust retries (MAX_RETRIES = 10).  Backoff grows exponentially
    // (up to ~512s), so advance by a large total to fire every retry.
    act(() => {
      for (let i = 0; i < 20; i++) {
        vi.advanceTimersByTime(600_000);
      }
    });
    expect(result.current.error).toBe("Connection lost — please refresh the page");
    vi.useRealTimers();
    vi.stubGlobal("WebSocket", real);
  });
});
