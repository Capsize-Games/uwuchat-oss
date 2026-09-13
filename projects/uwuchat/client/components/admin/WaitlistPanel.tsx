/**
 * WaitlistPanel — view the waitlist queue and release invite batches.
 */

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "../../hooks/useAuth";
import {
  listWaitlist,
  releaseInvites,
  type WaitlistList,
} from "../../../../../extensions/auth/client/admin-api";
import styles from "./WaitlistPanel.module.css";

export default function WaitlistPanel() {
  const { accessToken } = useAuth();
  const [data, setData] = useState<WaitlistList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [releaseCount, setReleaseCount] = useState(10);
  const [releasing, setReleasing] = useState(false);
  const [lastRelease, setLastRelease] = useState<string[] | null>(null);

  const fetchData = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const result = await listWaitlist();
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

  async function handleRelease() {
    if (!accessToken || releaseCount < 1) return;
    setReleasing(true);
    setError(null);
    try {
      const result = await releaseInvites(releaseCount);
      setLastRelease(result.emails);
      await fetchData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Release failed");
    } finally {
      setReleasing(false);
    }
  }

  if (loading) return <p className="text-secondary p-3">Loading…</p>;
  if (error) return <p className="text-danger p-3">{error}</p>;
  if (!data) return null;

  return (
    <div className={styles.wrapper}>
      <h2 className={styles.heading}>Waitlist</h2>

      {/* Summary bar */}
      <div className={styles.summaryBar}>
        <span>Total: <strong>{data.total}</strong></span>
        <span className={styles.summaryWaiting}>Waiting: <strong>{data.waiting}</strong></span>
        <span className={styles.summaryInvited}>Invited: <strong>{data.invited}</strong></span>
        <span className={styles.summaryConverted}>Converted: <strong>{data.converted}</strong></span>
      </div>

      {/* Release control */}
      <div className={styles.releaseRow}>
        <label className={styles.releaseLabel}>Release</label>
        <input
          type="number"
          min={1}
          max={data.waiting || 1}
          value={releaseCount}
          onChange={(e) => setReleaseCount(Number(e.target.value) || 1)}
          className={styles.releaseInput}
        />
        <button
          type="button"
          className={`btn btn-sm btn-primary ${styles.releaseBtn}`}
          onClick={handleRelease}
          disabled={releasing || releaseCount < 1}
        >
          {releasing ? "Releasing…" : "Release"}
        </button>
      </div>

      {lastRelease && (
        <div className={styles.releaseResult}>
          Released {lastRelease.length} invite{lastRelease.length !== 1 ? "s" : ""}
          : {lastRelease.join(", ")}
        </div>
      )}

      {/* Entry list */}
      <div className={styles.scrollTable}>
        <table className={styles.entryTable}>
          <thead>
            <tr className={styles.entryHeader}>
              <th>Email</th>
              <th>Status</th>
              <th>Invited</th>
            </tr>
          </thead>
          <tbody>
            {data.entries.map((entry) => (
              <tr key={entry.id} className={styles.entryRow}>
                <td>{entry.email}</td>
                <td>
                  <span
                    className={
                      entry.status === "converted"
                        ? styles.statusConverted
                        : entry.status === "invited"
                          ? styles.statusInvited
                          : styles.statusWaiting
                    }
                  >
                    {entry.status}
                  </span>
                </td>
                <td>
                  {entry.invited_at
                    ? new Date(entry.invited_at).toLocaleDateString()
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
