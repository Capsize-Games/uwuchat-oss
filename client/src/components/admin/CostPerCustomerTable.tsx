/** Per-customer cost breakdown table for the cost-tracking panel. */

import type { PerCustomer } from "./costTrackingTypes";
import { costBarStyle, formatCost } from "./costHelpers";
import styles from "./CostPerCustomerTable.module.css";

interface Props {
  data: PerCustomer | null;
}

export default function CostPerCustomerTable({ data }: Props) {
  if (!data || data.accounts.length === 0) return null;

  const maxCost = Math.max(
    ...data.accounts.map((a) => a.total_cost_usd),
    0,
  );

  return (
    <div className={styles.card}>
      <h5 className={styles.heading}>Requests by Customer</h5>
      {/*
        Per-account requests — billing unit is one request (a
        call_chain_id), not a raw LLM call. Cost stats only cover
        requests where every call in the chain was priced, since a
        partially-priced chain would understate the real cost.
      */}
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Account</th>
            <th>Requests</th>
            <th>Priced</th>
            <th className={styles.costCol}>Total Cost</th>
            <th className={styles.costCol}>Avg Cost/Request</th>
          </tr>
        </thead>
        <tbody>
          {data.accounts.map((a) => (
            <tr key={a.account_id}>
              <td>{a.email ?? `#${a.account_id}`}</td>
              <td>{a.total_requests.toLocaleString()}</td>
              <td>{a.priced_requests.toLocaleString()}</td>
              <td className={styles.costCol}>
                <div style={costBarStyle(a.total_cost_usd, maxCost)}>
                  {formatCost(a.total_cost_usd)}
                </div>
              </td>
              <td className={styles.costCol}>
                {a.avg_cost_per_request_usd != null
                  ? formatCost(a.avg_cost_per_request_usd)
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
