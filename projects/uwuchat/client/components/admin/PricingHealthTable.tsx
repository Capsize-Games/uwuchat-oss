import { request } from "@/api/client-base";
import styles from "./PricingHealthTable.module.css";

interface PricingHealthEntry {
  model_id: string; status: string; input_price_per_mtok: number; output_price_per_mtok: number;
  total_input_tokens: number; total_output_tokens: number; pipeline_keys: string[];
}
export interface PricingHealthResponse { models_in_use: number; models_missing_pricing: number; entries: PricingHealthEntry[]; }

interface Props { data: PricingHealthResponse; checking: boolean; onFix: () => void; }

export function PricingHealthTable({ data, checking, onFix }: Props) {
  return (
    <div className={styles.section}>
      <div className={styles.header}>
        <span>PRICING HEALTH</span>
        {data.models_missing_pricing > 0 && <button onClick={onFix} disabled={checking} className={styles.fixBtn}>Fix {data.models_missing_pricing} issue{data.models_missing_pricing !== 1 ? "s" : ""}</button>}
      </div>
      <table className={styles.table}>
        <thead><tr className={styles.hdrRow}><th className={styles.hdrCell}>Model</th><th className={styles.hdrCellRight}>In/$MTok</th><th className={styles.hdrCellRight}>Out/$MTok</th><th className={styles.hdrCellCenter}>Status</th></tr></thead>
        <tbody>
          {data.entries.map((e) => (
            <tr key={e.model_id} className={styles.trRow}>
              <td className={styles.modelCell}>{e.model_id}</td>
              <td className={e.status === "$0" ? styles.priceZero : styles.priceOk}>{e.input_price_per_mtok.toFixed(4)}</td>
              <td className={e.status === "$0" ? styles.priceZero : styles.priceOk}>{e.output_price_per_mtok.toFixed(4)}</td>
              <td className={e.status === "OK" ? styles.statusOk : styles.statusBad}>{e.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className={styles.footer}>{data.models_in_use} model{data.models_in_use !== 1 ? "s" : ""} in use</div>
    </div>
  );
}

export async function fetchPricingHealth(): Promise<PricingHealthResponse> { return request<PricingHealthResponse>("GET", "/api/v1/admin/pricing-health"); }
export async function fixPricingHealth(): Promise<PricingHealthResponse> { return request<PricingHealthResponse>("POST", "/api/v1/admin/pricing-health/fix"); }
