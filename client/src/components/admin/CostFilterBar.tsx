/** Filter bar for the cost-tracking panel. */

import type { AccountOption } from "./costTrackingTypes";
import styles from "./CostTrackingPanel.module.css";

interface Props {
  days: number;
  setDays: (v: number) => void;
  filterPkey: string;
  setFilterPkey: (v: string) => void;
  filterModel: string;
  setFilterModel: (v: string) => void;
  filterAccount: string;
  setFilterAccount: (v: string) => void;
  pipelineOptions: string[];
  modelOptions: string[];
  accounts: AccountOption[];
  loading: boolean;
  onRefresh: () => void;
}

export default function CostFilterBar({
  days,
  setDays,
  filterPkey,
  setFilterPkey,
  filterModel,
  setFilterModel,
  filterAccount,
  setFilterAccount,
  pipelineOptions,
  modelOptions,
  accounts,
  loading,
  onRefresh,
}: Props) {
  return (
    <div className={styles.controls}>
      <label className={styles.label}>
        Days
        <input
          type="number"
          value={days}
          onChange={(e) =>
            setDays(parseInt(e.target.value, 10) || 30)
          }
          className={styles.input}
        />
      </label>
      <label className={styles.label}>
        Pipeline
        <select
          value={filterPkey}
          onChange={(e) => setFilterPkey(e.target.value)}
          className={styles.input}
        >
          <option value="">All</option>
          {pipelineOptions.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.label}>
        Model
        <select
          value={filterModel}
          onChange={(e) => setFilterModel(e.target.value)}
          className={styles.input}
        >
          <option value="">All</option>
          {modelOptions.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.label}>
        Account
        <select
          value={filterAccount}
          onChange={(e) => setFilterAccount(e.target.value)}
          className={styles.input}
        >
          <option value="">All</option>
          {accounts.map((a) => (
            <option key={a.account_id} value={a.account_id}>
              {a.email ?? `#${a.account_id}`}
            </option>
          ))}
        </select>
      </label>
      <button
        onClick={onRefresh}
        className={styles.btn}
        disabled={loading}
      >
        {loading ? "Loading…" : "Refresh"}
      </button>
    </div>
  );
}
