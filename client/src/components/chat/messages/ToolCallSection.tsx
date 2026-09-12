import { useState } from "react";
import type { ParsedToolCall } from "../toolCallUtils";
import styles from "./ToolCallSection.module.css";

export default function ToolCallSection({
  toolCall,
  result,
  defaultExpanded,
}: {
  toolCall: ParsedToolCall;
  result?: string | null;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded ?? false);

  return (
    <div className={`mb-2 rounded ${styles.card} ${styles.cardTool}`}>
      <div
        className="d-flex align-items-center gap-1 p-1 cursor-pointer user-select-none"
        onClick={() => setExpanded((e) => !e)}
        role="button"
      >
        <span>{expanded ? "▼" : "▶"}</span>
        <span>🔧</span>
        <span className={`text-theme-secondary ${styles.headerLabel}`}>
          Tool Call: {toolCall.functionName}
        </span>
      </div>
      {expanded && (
        <div className={`p-2 ${styles.body}`}>
          {Object.entries(toolCall.parameters).map(([key, value]) => (
            <div key={key} className={styles.fieldGroup}>
              <div className={styles.fieldLabel}>{key}</div>
              <div className={styles.fieldValue}>{value}</div>
            </div>
          ))}
          {result && (
            <div className={styles.resultSection}>
              <div className={styles.resultLabel}>
                result
              </div>
              <div className={styles.resultValue}>
                {result}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
