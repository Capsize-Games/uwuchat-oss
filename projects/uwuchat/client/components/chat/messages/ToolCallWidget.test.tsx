import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ToolCallWidget from "./ToolCallWidget";
import type { ToolCallRecord } from "../../../types/api";

describe("ToolCallWidget", () => {
  it("renders the tool name and status", () => {
    const tool: ToolCallRecord = {
      tool_id: "tc-1",
      tool_name: "execute_command",
      status: "completed",
      details: "src/\nfile.ts",
    };
    render(<ToolCallWidget tool={tool} />);
    expect(screen.getByText("Execute Command")).toBeTruthy();
    expect(screen.getByText("done")).toBeTruthy();
  });

  it("is collapsed by default and expands on click", () => {
    const tool: ToolCallRecord = {
      tool_id: "tc-1",
      tool_name: "execute_command",
      status: "completed",
      details: "src/\nfile.ts",
    };
    render(<ToolCallWidget tool={tool} />);
    // Result hidden until expanded.
    expect(screen.queryByText("src/")).toBeNull();
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText(/src\//)).toBeTruthy();
    expect(screen.getByText(/file\.ts/)).toBeTruthy();
  });

  it("shows error styling and error text", () => {
    const tool: ToolCallRecord = {
      tool_id: "tc-2",
      tool_name: "execute_command",
      status: "error",
      details: "Tool error: All connection attempts failed",
    };
    const { container } = render(<ToolCallWidget tool={tool} />);
    expect(screen.getByText("error")).toBeTruthy();
    // Error class applied.
    expect(container.querySelector(".widget.error")).toBeTruthy();
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText(/All connection attempts failed/)).toBeTruthy();
  });

  it("shows query when present", () => {
    const tool: ToolCallRecord = {
      tool_id: "tc-3",
      tool_name: "execute_command",
      status: "completed",
      details: "ok",
      query: "pwd && ls",
    };
    render(<ToolCallWidget tool={tool} />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("pwd && ls")).toBeTruthy();
  });

  it("shows 'no output' when details are empty", () => {
    const tool: ToolCallRecord = {
      tool_id: "tc-4",
      tool_name: "list_files",
      status: "completed",
      details: null,
    };
    render(<ToolCallWidget tool={tool} />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("no output")).toBeTruthy();
  });
});
