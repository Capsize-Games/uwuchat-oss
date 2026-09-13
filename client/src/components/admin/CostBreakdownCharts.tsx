/** Cost breakdown charts — pipeline and model breakdown as CSS bar
 *  charts, built from the in-memory `summary` array (no new API
 *  calls).  Consistent with the cost-bar heat treatment already
 *  established in `costHelpers.ts`. */

import { useMemo } from "react";
import type { SummaryRow } from "./costTrackingTypes";
import styles from "./CostBreakdownCharts.module.css";

interface Props {
  summary: SummaryRow[];
}

interface GroupEntry {
  label: string;
  cost: number;
}

/** Group summary rows by a key-extractor, summing cost_usd per group,
 *  then sort descending by cost. */
function groupBy(
  rows: SummaryRow[],
  keyFn: (r: SummaryRow) => string,
): GroupEntry[] {
  const map = new Map<string, number>();
  for (const r of rows) {
    const k = keyFn(r);
    map.set(k, (map.get(k) ?? 0) + r.cost_usd);
  }
  return Array.from(map.entries())
    .map(([label, cost]) => ({ label, cost }))
    .sort((a, b) => b.cost - a.cost);
}

export default function CostBreakdownCharts({ summary }: Props) {
  const byPipeline = useMemo(
    () => groupBy(summary, (r) => r.pipeline_key),
    [summary],
  );
  const byModel = useMemo(
    () => groupBy(summary, (r) => r.model_id),
    [summary],
  );

  const totalCost = byPipeline.reduce(
    (s, e) => s + e.cost, 0,
  );

  return (
    <div className={styles.row}>
      <BarChartCard
        title="Cost by Pipeline"
        entries={byPipeline}
        totalCost={totalCost}
      />
      <BarChartCard
        title="Cost by Model"
        entries={byModel}
        totalCost={totalCost}
      />
    </div>
  );
}

function BarChartCard({
  title,
  entries,
  totalCost,
}: {
  title: string;
  entries: GroupEntry[];
  totalCost: number;
}) {
  const maxCost = entries.length > 0 ? entries[0].cost : 1;

  return (
    <div className={styles.card}>
      <h5 className={styles.heading}>{title}</h5>
      <div className={styles.barList}>
        {entries.length === 0 && (
          <span className={styles.empty}>No data</span>
        )}
        {entries.map((e) => {
          const pct =
            totalCost > 0
              ? ((e.cost / totalCost) * 100).toFixed(1)
              : "0.0";
          const barWidth =
            totalCost > 0
              ? (e.cost / maxCost) * 100
              : 0;
          return (
            <div key={e.label} className={styles.barRow}>
              <span className={styles.barLabel}>
                {e.label}
              </span>
              <div className={styles.barTrack}>
                <div
                  className={styles.barFill}
                  // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
                  style={{ width: `${barWidth}%` }}
                />
              </div>
              <span className={styles.barValue}>
                ${e.cost.toFixed(4)}
                <span className={styles.barPct}>
                  {" "}
                  ({pct}%)
                </span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
