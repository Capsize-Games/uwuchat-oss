import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import StreamingMessageBubble from "./StreamingMessageBubble";

describe("StreamingMessageBubble inline tool placement", () => {
  const tool = (over: Record<string, unknown> = {}) => ({
    tool_id: "tc-1",
    tool_name: "execute_command",
    status: "completed",
    details: "output",
    ...over,
  });

  it("renders narration and the widget when its position is reached", () => {
    render(
      <StreamingMessageBubble
        content="I'll check it."
        toolEvents={[tool({ position: 10 })]}
      />,
    );
    expect(screen.getByText("Execute Command")).toBeTruthy();
  });

  it("does NOT render a widget before its position is reached", () => {
    render(
      <StreamingMessageBubble
        content="I'll check."
        toolEvents={[tool({ position: 50 })]}
      />,
    );
    // Reveal is at 10 chars — position 50 not yet reached.
    expect(screen.queryByText("Execute Command")).toBeNull();
  });

  it("interleaves the widget inline between narration segments", () => {
    const { container } = render(
      <StreamingMessageBubble
        content="Before. After."
        toolEvents={[tool({ position: 8 })]}
      />,
    );
    const text = container.textContent ?? "";
    // Narration before the position + widget + narration after.
    expect(text).toContain("Before.");
    expect(text).toContain("After.");
    expect(text.indexOf("Before.")).toBeLessThan(
      text.indexOf("Execute Command"),
    );
    expect(text.indexOf("Execute Command")).toBeLessThan(
      text.indexOf("After."),
    );
  });

  it("appends widgets after text when no position is stamped", () => {
    const { container } = render(
      <StreamingMessageBubble content="Narration only." toolEvents={[tool()]} />,
    );
    const text = container.textContent ?? "";
    expect(text.indexOf("Narration only.")).toBeLessThan(
      text.indexOf("Execute Command"),
    );
  });
});
