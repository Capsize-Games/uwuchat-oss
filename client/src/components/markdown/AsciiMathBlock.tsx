import type { JSX } from "react";

interface AsciiMathBlockProps {
  content: string;
}

/**
 * Renders an AsciiMath fenced code block.
 *
 * Full MathJax rendering of AsciiMath is not available client-side
 * because mathjax-full is a CJS/Node.js library incompatible with
 * Vite's ESM browser bundling.  The AsciiMath content is displayed
 * as readable pre-formatted text — the user can still read it
 * directly (AsciiMath is designed to be human-readable).
 */
export function AsciiMathBlock({
  content,
}: AsciiMathBlockProps): JSX.Element {
  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        <span className="code-block-lang">AsciiMath</span>
      </div>
      <pre className="code-block-pre">
        <code>{content}</code>
      </pre>
    </div>
  );
}
