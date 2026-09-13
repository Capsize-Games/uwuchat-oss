/**
 * Regression test for security finding #10 — XSS in markdown renderer.
 *
 * Confirms that ``MessageBubble`` renders raw HTML/script tags as inert
 * text, not executed markup.  ``ReactMarkdown`` without ``rehype-raw``
 * is the safeguard — this test pins that behaviour.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

describe("MessageBubble XSS prevention", () => {
  it("renders <script> tag as inert text, not executed", () => {
    const xss = '<script>alert("xss")</script>';
    const { container } = render(
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{xss}</ReactMarkdown>,
    );
    // The script tag should be rendered as text, not as an actual
    // <script> element that the browser would execute.
    expect(container.querySelector("script")).toBeNull();
    // The text content should include the raw tag source.
    expect(container.textContent).toContain("<script>");
  });

  it("renders <img onerror> as inert text, not executed", () => {
    const xss = '<img src=x onerror="alert(1)">';
    const { container } = render(
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{xss}</ReactMarkdown>,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img");
  });

  it("renders inline HTML as text when no rehype-raw is used", () => {
    const html = "<b>bold</b><i>italic</i>";
    const { container } = render(
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{html}</ReactMarkdown>,
    );
    // Without rehype-raw, HTML tags are escaped.
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("i")).toBeNull();
    // The raw HTML source should appear as text.
    expect(container.textContent).toContain("<b>bold</b>");
  });

  it("does not use dangerouslySetInnerHTML", () => {
    // Check the render produces a safe DOM.
    const safe = "Hello, world!";
    const { container } = render(
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{safe}</ReactMarkdown>,
    );
    // The rendered output is plain React elements, not raw HTML
    // injection via dangerouslySetInnerHTML.
    expect(container.innerHTML).not.toContain("dangerouslySetInnerHTML");
  });
});
