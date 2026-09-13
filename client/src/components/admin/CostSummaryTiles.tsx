/** Summary stat tiles for the cost-tracking panel. */

import type { PerCustomer } from "./costTrackingTypes";
import styles from "./CostSummaryTiles.module.css";

interface Props {
  totalCost: number;
  totalCalls: number;
  avgCost: number;
  pricedCalls: number;
  perCustomer: PerCustomer | null;
}

export default function CostSummaryTiles({
  totalCost,
  totalCalls,
  avgCost,
  pricedCalls,
  perCustomer,
}: Props) {
  return (
    <div className={styles.wrap}>
      <Tile label="Total Cost" value={`$${totalCost.toFixed(4)}`} />
      <Tile
        label="Call Count"
        value={totalCalls.toLocaleString()}
      />
      <Tile
        label={`Avg Cost/Call (${pricedCalls} priced)`}
        value={`$${avgCost.toFixed(6)}`}
      />
      <Tile
        label="Customers"
        value={perCustomer?.distinct_tenants?.toLocaleString() ?? "—"}
      />
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.tile}>
      <div className={styles.label}>{label}</div>
      <div className={styles.value}>{value}</div>
    </div>
  );
}
