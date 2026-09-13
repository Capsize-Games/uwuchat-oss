import "katex/dist/katex.min.css";

import { useState, useEffect, useMemo, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeHighlight from "rehype-highlight";
import type { PluggableList } from "unified";
import { CodeBlock } from "./CodeBlock";

interface ChatMarkdownProps {
  content: string;
  streaming?: boolean;
}

/**
 * Passthrough component that replaces ReactMarkdown's default <pre>.
 *
 * ReactMarkdown wraps fenced code blocks in its own <pre>, but CodeBlock
 * already provides its own <pre> wrapper.  Without this override every
 * fenced code block ends up with nested <pre> elements.
 */
function PrePassthrough({
  children,
}: {
  children?: React.ReactNode;
}): React.JSX.Element {
  return <>{children}</>;
}

/**
 * Returns true once content has been stable for `delay` ms.
 *
 * Uses an always-async timer pattern (setTimeout with 0ms when not
 * streaming) to avoid the react-hooks/set-state-in-effect lint rule.
 */
function useDebouncedStable(
  content: string,
  streaming: boolean,
  delay = 250,
): boolean {
  const [stableContent, setStableContent] = useState(
    streaming ? "" : content,
  );
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    const d = streaming ? delay : 0;
    timerRef.current = setTimeout(() => {
      setStableContent(content);
    }, d);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [content, streaming, delay]);

  return stableContent === content;
}

export default function ChatMarkdown({
  content,
  streaming = false,
}: ChatMarkdownProps) {
  const isStable = useDebouncedStable(content, streaming);

  const rehypePlugins: PluggableList = useMemo(() => {
    if (!isStable) return [];
    return [rehypeKatex, rehypeHighlight];
  }, [isStable]);

  const remarkPlugins: PluggableList = useMemo(() => {
    if (!isStable) return [remarkGfm];
    // singleDollarTextMath: false prevents $...$ from being parsed
    // as inline KaTeX math (which would strip spaces and render
    // dollar amounts like $50K in italic serif).  Only $$...$$
    // display math is supported.
    return [remarkGfm, [remarkMath, { singleDollarTextMath: false }]];
  }, [isStable]);

  const components = useMemo(
    () => ({
      code: CodeBlock,
      pre: PrePassthrough,
    }),
    [],
  );

  return (
    <ReactMarkdown
      remarkPlugins={remarkPlugins}
      rehypePlugins={rehypePlugins}
      components={components}
    >
      {content}
    </ReactMarkdown>
  );
}
