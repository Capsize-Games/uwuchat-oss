/**
 * Unit tests for ChatMarkdown and related markdown-rendering components.
 *
 * Covers:
 * - LaTeX inline/display renders without throwing
 * - AsciiMath fenced block renders without throwing
 * - Fenced code block renders with language label and copy button
 * - Malformed LaTeX does not crash the render
 * - Inline code renders plain <code>
 * - XSS safety preserved (HTML is not injected)
 * - Single <pre> per fenced code block (no nesting)
 */
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import ChatMarkdown from "@/components/markdown/ChatMarkdown";
import MathBlock from "@/components/markdown/MathBlock";

describe("ChatMarkdown", () => {
  describe("LaTeX rendering", () => {
    it("renders single-dollar text literally, not as inline math", () => {
      // singleDollarTextMath is intentionally disabled (see
      // ChatMarkdown.tsx) so dollar amounts like "$50K" don't render
      // as italic math. $...$ content must pass through unchanged.
      const content = "The identity is $e^{i\\pi} + 1 = 0$.";
      const { container } = render(
        <ChatMarkdown content={content} />,
      );
      expect(container.textContent).toBe(
        "The identity is $e^{i\\pi} + 1 = 0$.",
      );
      expect(container.querySelector(".katex")).toBeNull();
    });

    it("renders display LaTeX without throwing", () => {
      const content =
        "$$\\int_0^\\infty e^{-x^2}\\,dx = \\frac{\\sqrt{\\pi}}{2}$$";
      const { container } = render(
        <ChatMarkdown content={content} />,
      );
      expect(container.textContent).toBeTruthy();
      // Display math should produce KaTeX output.
      expect(container.querySelector(".katex")).toBeTruthy();
    });

    it("renders underscore/asterisk text without Markdown corruption", () => {
      // Single-dollar math is disabled (see test above), so this
      // must pass through as literal text -- neither consumed as
      // KaTeX nor as Markdown emphasis syntax.
      const content = "$a_i * b_i$";
      const { container } = render(
        <ChatMarkdown content={content} />,
      );
      expect(container.querySelector("em")).toBeNull();
      expect(container.querySelector(".katex")).toBeNull();
      expect(container.textContent).toBe("$a_i * b_i$");
    });

    it("does not crash on malformed LaTeX", () => {
      const content = "Bad math: $\\frac{1}{$";
      // Should render without throwing.
      expect(() =>
        render(<ChatMarkdown content={content} />),
      ).not.toThrow();
    });
  });

  describe("code block rendering", () => {
    it("renders fenced code block with language label and copy button", () => {
      const content = '```python\nprint("hello")\n```';
      const { container } = render(
        <ChatMarkdown content={content} />,
      );
      // Language label.
      expect(container.textContent).toContain("Python");
      // Copy button.
      const btn = container.querySelector(".code-block-copy-btn");
      expect(btn).toBeTruthy();
      expect(btn?.textContent).toContain("Copy");
    });

    it("renders inline code as plain <code>", () => {
      const content = "Use `const x = 1` for constants.";
      const { container } = render(
        <ChatMarkdown content={content} />,
      );
      const codeEl = container.querySelector("code");
      expect(codeEl).toBeTruthy();
      // Should not have a code-block-wrapper around inline code.
      expect(
        container.querySelector(".code-block-wrapper"),
      ).toBeNull();
    });

    it("produces exactly one <pre> per fenced code block (no nesting)", () => {
      const content = '```python\nprint("hello")\n```';
      const { container } = render(
        <ChatMarkdown content={content} />,
      );
      const pres = container.querySelectorAll("pre");
      expect(pres.length).toBe(1);
    });
  });

  describe("AsciiMath fenced block", () => {
    it("renders asciimath fenced block without throwing", () => {
      const content = "```asciimath\nsqrt(2) = 1.41421356\n```";
      // Should render without throwing. AsciiMath is displayed as
      // a styled code block.
      expect(() =>
        render(<ChatMarkdown content={content} />),
      ).not.toThrow();
    });
  });

  describe("XSS safety", () => {
    it("renders HTML tags as inert text", () => {
      const content = '<script>alert("xss")</script>';
      const { container } = render(
        <ChatMarkdown content={content} />,
      );
      // <script> should not appear as a real DOM element.
      expect(container.querySelector("script")).toBeNull();
    });
  });

  describe("streaming mode", () => {
    it("renders without full pipeline when streaming", () => {
      const content = "Streaming $x^2$ content";
      const { container } = render(
        <ChatMarkdown content={content} streaming />,
      );
      // In streaming mode, math is not processed immediately,
      // so no .katex span should be present.
      expect(
        container.querySelector(".katex"),
      ).toBeNull();
    });
  });
});

describe("MathBlock error boundary", () => {
  it("renders children when no error", () => {
    const { container } = render(
      <MathBlock>
        <span data-testid="math-content">E=mc²</span>
      </MathBlock>,
    );
    expect(container.textContent).toContain("E=mc²");
  });

  it("renders fallback when error is thrown", () => {
    function Thrower(): never {
      throw new Error("MathJax error");
    }
    // Suppress console.error for the expected error boundary catch.
    const prev = console.error;
    console.error = () => {};
    try {
      const { container } = render(
        <MathBlock>
          <Thrower />
        </MathBlock>,
      );
      expect(container.textContent).toContain(
        "Math rendering error",
      );
    } finally {
      console.error = prev;
    }
  });
});
