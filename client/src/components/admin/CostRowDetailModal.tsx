/** Row-expand modal showing per-call metadata (char counts, not content). */

import type { UsageRow } from "./costTrackingTypes";
import styles from "./CostRowDetailModal.module.css";

interface Props {
  row: UsageRow;
  onClose: () => void;
}

export default function CostRowDetailModal({ row, onClose }: Props) {
  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <strong>
            {row.pipeline_key} — {row.model_id}
            {row.recorded_at
              ? ` — ${row.recorded_at.slice(0, 19)}`
              : ""}
          </strong>
          <button onClick={onClose} className={styles.btn}>
            Close
          </button>
        </div>
        <div className={styles.row}>
          <span>Input tokens: {row.input_tokens.toLocaleString()}</span>
          <span>Output tokens: {row.output_tokens.toLocaleString()}</span>
        </div>
        <div className={styles.row}>
          <span>Prompt chars: {row.prompt_char_count ?? "(not recorded)"}</span>
          <span>Response chars: {row.response_char_count ?? "(not recorded)"}</span>
        </div>
        {row.cost_usd != null && (
          <div className={styles.labelMargin}>
            Cost: ${row.cost_usd.toFixed(8)}
          </div>
        )}
      </div>
    </div>
  );
}
