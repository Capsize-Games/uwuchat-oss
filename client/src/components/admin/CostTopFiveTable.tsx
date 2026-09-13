/** Top-5-by-cost table for the cost-tracking panel. */

import type { SummaryRow } from "./costTrackingTypes";
import { costBarStyle, formatCost } from "./costHelpers";
import styles from "./CostTopFiveTable.module.css";

interface Props {
  rows: SummaryRow[];
}

export default function CostTopFiveTable({ rows }: Props) {
  if (rows.length === 0) return null;

  const maxCost = Math.max(...rows.map((r) => r.cost_usd), 0);

  return (
    <div className={styles.card}>
      <h5 className={styles.heading}>Top 5 by Cost</h5>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Pipeline</th>
            <th>Model</th>
            <th>Calls</th>
            <th>In Tokens</th>
            <th>Out Tokens</th>
            <th className={styles.costCol}>Cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{r.pipeline_key}</td>
              <td className={styles.mono}>{r.model_id}</td>
              <td>{r.call_count.toLocaleString()}</td>
              <td>{r.total_input_tokens.toLocaleString()}</td>
              <td>{r.total_output_tokens.toLocaleString()}</td>
              <td className={styles.costCol}>
                <div style={costBarStyle(r.cost_usd, maxCost)}>
                  {formatCost(r.cost_usd)}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
