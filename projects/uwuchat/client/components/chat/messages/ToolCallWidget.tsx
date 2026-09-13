import { useState } from "react";
import type { ToolCallRecord } from "../../../types/api";
import styles from "./ToolCallWidget.module.css";

interface Props {
  tool: ToolCallRecord;
}

function toolLabel(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function prettyQuery(tool: ToolCallRecord): string {
  if (tool.query) return tool.query;
  // Fall back to a generic description.
  return "";
}

/**
 * Collapsible inline widget showing one tool call + its result.
 * Rendered inside an assistant message bubble wherever a tool ran.
 */
export default function ToolCallWidget({ tool }: Props) {
  const [open, setOpen] = useState(false);
  const isError = tool.status === "error";
  const isDone = tool.status === "completed";

  return (
    <div className={`${styles.widget} ${isError ? styles.error : ""}`}>
      <button
        type="button"
        className={styles.header}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className={`${styles.statusDot} ${isError ? styles.dotError : isDone ? styles.dotDone : styles.dotRun}`} />
        <span className={styles.name}>{toolLabel(tool.tool_name)}</span>
        <span className={styles.statusText}>
          {isError ? "error" : isDone ? "done" : "running"}
        </span>
        <span className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`}>▾</span>
      </button>

      {open && (
        <div className={styles.body}>
          {prettyQuery(tool) && (
            <div className={styles.query}>
              <span className={styles.label}>command / query</span>
              <pre className={styles.pre}>{prettyQuery(tool)}</pre>
            </div>
          )}
          {tool.details ? (
            <div className={styles.result}>
              <span className={styles.label}>result</span>
              <pre className={styles.pre}>{tool.details}</pre>
            </div>
          ) : (
            <div className={styles.empty}>no output</div>
          )}
        </div>
      )}
    </div>
  );
}
