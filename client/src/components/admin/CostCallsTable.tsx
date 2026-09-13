/** Individual Calls table — the highest-priority readability fix.
 *
 * Changes from the original dense layout:
 *  - Prompt/Response previews removed from inline row (they are
 *    available in the expand modal — 1 click away).
 *  - In/Out tokens combined into one "Tokens" cell.
 *  - Cost column gets a subtle background-intensity bar matching
 *    other tables.
 *  - Whole row is clickable to open the detail modal, so the
 *    separate Expand button is replaced by a compact arrow indicator.
 *  - Column count reduced from 10 to 7 — fits one screen width
 *    without horizontal scroll at a normal viewport.
 */

import type { UsageRow } from "./costTrackingTypes";
import { costBarStyle, formatCost } from "./costHelpers";
import styles from "./CostCallsTable.module.css";

interface Props {
  rows: UsageRow[];
  onExpand: (row: UsageRow) => void;
}

export default function CostCallsTable({ rows, onExpand }: Props) {
  if (rows.length === 0) return null;

  const maxCost = Math.max(
    ...rows.map((r) => (r.cost_usd != null ? r.cost_usd : 0)),
    0,
  );

  return (
    <table className={styles.table}>
      <thead className={styles.thead}>
        <tr>
          <th>Time</th>
          <th>Pipeline</th>
          <th>Model</th>
          <th>Acct</th>
          <th>Tokens</th>
          <th className={styles.costCol}>Cost</th>
          <th className={styles.expandCol} />
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr
            key={r.id ?? Math.random()}
            onClick={() => onExpand(r)}
            className={styles.row}
          >
            <td className={styles.nowrap}>
              {r.recorded_at
                ? r.recorded_at.slice(0, 19)
                : "—"}
            </td>
            <td>{r.pipeline_key}</td>
            <td className={styles.mono}>
              {r.model_id.slice(0, 40)}
            </td>
            <td>{r.account_id ?? "—"}</td>
            <td className={styles.nowrap}>
              {r.input_tokens.toLocaleString()}→
              {r.output_tokens.toLocaleString()}
            </td>
            <td className={styles.costCol}>
              {r.cost_usd != null ? (
                <div
                  style={costBarStyle(r.cost_usd, maxCost)}
                >
                  {formatCost(r.cost_usd)}
                </div>
              ) : (
                "—"
              )}
            </td>
            <td className={styles.expandCol}>→</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
