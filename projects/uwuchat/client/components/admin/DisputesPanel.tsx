/**
 * DisputesPanel — view Stripe disputes with evidence deadlines.
 */

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "../../hooks/useAuth";
import {
  listDisputes,
  type DisputeList,
} from "../../../../../extensions/auth/client/admin-api";
import styles from "./DisputesPanel.module.css";

export default function DisputesPanel() {
  const { accessToken } = useAuth();
  const [data, setData] = useState<DisputeList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const result = await listDisputes();
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) return <p className="text-secondary p-3">Loading…</p>;
  if (error) return <p className="text-danger p-3">{error}</p>;
  if (!data) return null;

  return (
    <div className={styles.wrapper}>
      <h2 className={styles.heading}>Disputes</h2>

      <div className={styles.summaryRow}>
        <span>Total: <strong>{data.total}</strong></span>
        <span className={styles.openCount}>
          Open: <strong>{data.open_count}</strong>
        </span>
      </div>

      {data.disputes.length === 0 && (
        <p className={`text-secondary ${styles.emptyText}`}>No disputes recorded.</p>
      )}

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr className={styles.tableHeader}>
              <th>Acct</th>
              <th>Amount</th>
              <th>Reason</th>
              <th>Status</th>
              <th>Evidence due</th>
            </tr>
          </thead>
          <tbody>
            {data.disputes.map((d) => (
              <tr key={d.id} className={styles.tableRow}>
                <td>
                  {d.account_id ?? "—"}
                </td>
                <td>
                  {d.amount != null
                    ? `$${(d.amount / 100).toFixed(2)}`
                    : "—"}
                </td>
                <td>
                  {d.reason ?? "—"}
                </td>
                <td>
                  <span className={
                    d.status === "won" ? styles.statusWon
                    : d.status === "lost" ? styles.statusLost
                    : styles.statusOpen
                  }>
                    {d.status}
                  </span>
                </td>
                <td>
                  {d.evidence_due_by
                    ? new Date(d.evidence_due_by).toLocaleDateString()
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
