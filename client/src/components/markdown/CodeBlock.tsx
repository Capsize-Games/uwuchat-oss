import { useCallback, useState } from "react";
import type { JSX } from "react";
import { AsciiMathBlock } from "./AsciiMathBlock";

interface CodeBlockProps {
  className?: string;
  children?: React.ReactNode;
  inline?: boolean;
}

function useCopyToClipboard() {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API may be unavailable; silently fail.
    }
  }, []);

  return { copied, copy };
}

function languageFromClassName(className?: string): string | null {
  if (!className) return null;
  const match = className.match(/language-(\S+)/);
  return match ? match[1] : null;
}

function extractTextContent(children: React.ReactNode): string {
  if (typeof children === "string") return children;
  if (Array.isArray(children)) {
    return children.map((c) => extractTextContent(c)).join("");
  }
  if (children && typeof children === "object" && "props" in children) {
    return extractTextContent(
      (children as { props: { children?: React.ReactNode } }).props.children,
    );
  }
  return "";
}

export function CodeBlock({
  className,
  children,
  inline,
}: CodeBlockProps): JSX.Element {
  const { copied, copy } = useCopyToClipboard();
  const language = languageFromClassName(className);
  const codeText = extractTextContent(children);

  const handleCopy = useCallback(() => {
    copy(codeText);
  }, [copy, codeText]);

  // Inline code: render plain <code>.
  if (inline || !language) {
    return <code className={className}>{children}</code>;
  }

  // AsciiMath fenced block: render via MathJax.
  if (language === "asciimath") {
    return <AsciiMathBlock content={codeText} />;
  }

  const langLabel = language.charAt(0).toUpperCase() + language.slice(1);

  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        <span className="code-block-lang">{langLabel}</span>
        <button
          type="button"
          className="code-block-copy-btn"
          onClick={handleCopy}
          title={copied ? "Copied!" : "Copy code"}
        >
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>
      <pre className="code-block-pre">
        <code className={className}>{children}</code>
      </pre>
    </div>
  );
}
