import { Component, type ReactNode } from "react";

interface MathBlockProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface MathBlockState {
  hasError: boolean;
}

/**
 * Error boundary that catches MathJax rendering failures.
 *
 * rehype-mathjax processes math at the HAST level and produces SVG, so
 * this component is not wired into the ReactMarkdown component map by
 * default (math rendering happens before React ever sees it).  It exists
 * as a safety net in case a future pipeline change introduces a React
 * math component override.
 */
export default class MathBlock extends Component<
  MathBlockProps,
  MathBlockState
> {
  constructor(props: MathBlockProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): MathBlockState {
    return { hasError: true };
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <span className="math-error">
            [Math rendering error]
          </span>
        )
      );
    }
    return this.props.children;
  }
}
