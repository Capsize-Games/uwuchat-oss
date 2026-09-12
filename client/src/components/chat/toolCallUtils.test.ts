import { describe, it, expect } from "vitest";
import { parseToolCallContent } from "./toolCallUtils";

describe("parseToolCallContent position tracking", () => {
  it("records start/end indices for inline widget placement", () => {
    const text = [
      "I'll read the file first.",
      "<tool_call>",
      "<function=read_file>",
      "<parameter=file_path>",
      "src/App.tsx",
      "</parameter>",
      "</function>",
      "</tool_call>",
      "I see the issue — the import is wrong.",
    ].join("\n");

    const { toolCalls, cleanContent } = parseToolCallContent(text);

    expect(toolCalls).toHaveLength(1);
    const tc = toolCalls[0];
    expect(tc.functionName).toBe("read_file");
    expect(tc.parameters.file_path).toBe("src/App.tsx");
    // The block starts after the first narration line + newline.
    expect(text.slice(tc.startIndex, tc.endIndex)).toBe(
      "<tool_call>\n<function=read_file>\n<parameter=file_path>\nsrc/App.tsx\n</parameter>\n</function>\n</tool_call>",
    );
    // Narration before and after the block is preserved (the trailing
    // newline after the joined block belongs to the join separator).
    expect(text.slice(0, tc.startIndex)).toBe("I'll read the file first.\n");
    expect(text.slice(tc.endIndex)).toBe(
      "\nI see the issue — the import is wrong.",
    );
    // cleanContent removes the block; the join newline before the block
    // and the leftover newline after it collapse to one blank line.
    expect(cleanContent).toBe(
      "I'll read the file first.\n\nI see the issue — the import is wrong.",
    );
  });

  it("tracks multiple tool calls in order", () => {
    const text = [
      "Let me check.",
      "<tool_call><function=execute_command><parameter=command>ls</parameter></function></tool_call>",
      "Then I'll read it.",
      "<tool_call><function=read_file><parameter=path>a.py</parameter></function></tool_call>",
      "Done.",
    ].join("\n");

    const { toolCalls } = parseToolCallContent(text);

    expect(toolCalls).toHaveLength(2);
    expect(toolCalls[0].functionName).toBe("execute_command");
    expect(toolCalls[1].functionName).toBe("read_file");
    // First call precedes the second.
    expect(toolCalls[0].startIndex).toBeLessThan(toolCalls[1].startIndex);
    // Narration between them is preserved by slicing.
    expect(
      text.slice(toolCalls[0].endIndex, toolCalls[1].startIndex),
    ).toBe("\nThen I'll read it.\n");
  });

  it("returns empty toolCalls for plain text", () => {
    const { toolCalls, cleanContent } = parseToolCallContent(
      "No tools here, just narration.",
    );
    expect(toolCalls).toHaveLength(0);
    expect(cleanContent).toBe("No tools here, just narration.");
  });
});
