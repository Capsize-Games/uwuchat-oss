/** Admin page: LLM cost tracking with summary, per-user breakdown,
 *  pipeline-key breakdown, and row-level drill-down.  Superuser only.
 *
 *  Orchestrator — delegates rendering to subcomponents to stay
 *  under the 250-line file cap. */

import { useState, useCallback, useEffect, useMemo } from "react";
import { request } from "@/api/client-base";
import type {
  SummaryRow,
  UsageRow,
  PaginatedRows,
  PerCustomer,
  AccountsList,
  AccountOption,
} from "./costTrackingTypes";
import styles from "./CostTrackingPanel.module.css";
import CostFilterBar from "./CostFilterBar";
import CostSummaryTiles from "./CostSummaryTiles";
import CostTopFiveTable from "./CostTopFiveTable";
import CostBreakdownCharts from "./CostBreakdownCharts";
import CostPerCustomerTable from "./CostPerCustomerTable";
import CostCallsTable from "./CostCallsTable";
import CostRowDetailModal from "./CostRowDetailModal";

const ROW_LIMIT = 50;

export default function CostTrackingPanel() {
  const [days, setDays] = useState(30);
  const [summary, setSummary] = useState<SummaryRow[]>([]);
  const [perCustomer, setPerCustomer] =
    useState<PerCustomer | null>(null);
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [rows, setRows] = useState<UsageRow[]>([]);
  const [rowTotal, setRowTotal] = useState(0);
  const [rowOffset, setRowOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterPkey, setFilterPkey] = useState("");
  const [filterModel, setFilterModel] = useState("");
  const [filterAccount, setFilterAccount] = useState("");
  const [expandedRow, setExpandedRow] =
    useState<UsageRow | null>(null);

  // ── fetch helpers ──────────────────────────────────────────────
  // request() resolves directly to the RPC response body (see
  // WsApiClient.ts pending.resolve(msg.body)) — no {status, body}
  // wrapper. Every fetch below reads the resolved value directly.

  const fetchSummary = useCallback(async () => {
    const data = await request<SummaryRow[]>(
      "GET", "/api/admin/token-usage/summary", { days },
    );
    setSummary(data);
  }, [days]);

  const fetchPerCustomer = useCallback(async () => {
    const data = await request<PerCustomer>(
      "GET", "/api/admin/token-usage/per-customer", { days },
    );
    setPerCustomer(data);
  }, [days]);

  const fetchAccounts = useCallback(async () => {
    const data = await request<AccountsList>(
      "GET", "/api/admin/token-usage/accounts", { days },
    );
    setAccounts(data.accounts);
  }, [days]);

  const fetchRows = useCallback(async (offset: number) => {
    const body: Record<string, unknown> = {
      days, limit: ROW_LIMIT, offset,
    };
    if (filterPkey) body.pipeline_key = filterPkey;
    if (filterModel) body.model_id = filterModel;
    if (filterAccount)
      body.account_id = parseInt(filterAccount, 10);
    const data = await request<PaginatedRows>(
      "GET", "/api/admin/token-usage/rows", body,
    );
    setRows(data.rows);
    setRowTotal(data.total);
    setRowOffset(offset);
  }, [days, filterPkey, filterModel, filterAccount]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await Promise.all([
        fetchSummary(), fetchPerCustomer(),
        fetchAccounts(), fetchRows(0),
      ]);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Load failed",
      );
    } finally {
      setLoading(false);
    }
  }, [fetchSummary, fetchPerCustomer, fetchAccounts, fetchRows]);

  useEffect(() => { loadAll(); }, []);

  // ── computed ────────────────────────────────────────────────────

  const totalCost = summary.reduce((s, r) => s + r.cost_usd, 0);
  const totalCalls = summary.reduce(
    (s, r) => s + r.call_count, 0,
  );
  // Calls made before cost tracking existed have no cost_usd — they
  // must not dilute the average, so divide by priced calls only.
  const pricedCalls = summary.reduce(
    (s, r) => s + r.priced_call_count, 0,
  );
  const avgCost = pricedCalls > 0 ? totalCost / pricedCalls : 0;
  const topFive = [...summary]
    .sort((a, b) => b.cost_usd - a.cost_usd)
    .slice(0, 5);

  const pipelineOptions = useMemo(
    () => [...new Set(summary.map((r) => r.pipeline_key))].sort(),
    [summary],
  );
  const modelOptions = useMemo(
    () => [...new Set(summary.map((r) => r.model_id))].sort(),
    [summary],
  );

  // ── render ──────────────────────────────────────────────────────

  return (
    <div className={styles.wrap}>
      <h4 className={styles.heading}>
        LLM Cost Tracking
      </h4>

      <CostFilterBar
        days={days} setDays={setDays}
        filterPkey={filterPkey}
        setFilterPkey={setFilterPkey}
        filterModel={filterModel}
        setFilterModel={setFilterModel}
        filterAccount={filterAccount}
        setFilterAccount={setFilterAccount}
        pipelineOptions={pipelineOptions}
        modelOptions={modelOptions}
        accounts={accounts}
        loading={loading}
        onRefresh={loadAll}
      />

      {error && <div className={styles.error}>{error}</div>}

      <CostSummaryTiles
        totalCost={totalCost} totalCalls={totalCalls}
        avgCost={avgCost} pricedCalls={pricedCalls}
        perCustomer={perCustomer}
      />

      <CostBreakdownCharts summary={summary} />
      <CostTopFiveTable rows={topFive} />
      <CostPerCustomerTable data={perCustomer} />

      {/* Row-level drill-down — flex:1 so it fills remaining space */}
      <div className={styles.card}>
        <h5 className={styles.cardHeading}>Individual Calls</h5>
        <div className={styles.pagination}>
          <span>
            Showing {rows.length} of {rowTotal} rows
          </span>
          {rowOffset > 0 && (
            <button
              onClick={() =>
                fetchRows(
                  Math.max(0, rowOffset - ROW_LIMIT),
                )
              }
              className={styles.btnSm}
            >
              ← Prev
            </button>
          )}
          {rowOffset + rows.length < rowTotal && (
            <button
              onClick={() =>
                fetchRows(rowOffset + ROW_LIMIT)
              }
              className={styles.btnSm}
            >
              Next →
            </button>
          )}
        </div>
        <div className={styles.scrollableTableWrap}>
          <CostCallsTable
            rows={rows} onExpand={setExpandedRow}
          />
        </div>
      </div>

      {expandedRow && (
        <CostRowDetailModal
          row={expandedRow}
          onClose={() => setExpandedRow(null)}
        />
      )}
    </div>
  );
}

export { CostTrackingPanel };
