import { useState } from "react";
import type { ConversationCostSummary } from "../../types/pipeline";
import styles from "./ConversationCostSummary.module.css";

interface Props { data: ConversationCostSummary | null; todayCost: ConversationCostSummary | null; }

const COLORS = ["#6c63ff", "#4ade80", "#f87171", "#facc15", "#38bdf8"];

export function ConversationCostSummary({ data, todayCost }: Props) {
  const [show30day, setShow30day] = useState(false);

  if (!data && !todayCost) return <div className={styles.card}><div className={styles.banner}>No usage data recorded yet. Send a few messages and refresh.</div></div>;

  return (
    <div className={styles.card}>
      <div className={styles.label}>TODAY</div>
      {todayCost ? <div className={styles.todayTotal}>${todayCost.total_cost_usd.toFixed(6)}</div> : <div className={styles.fallbackTotal}>$0.000000</div>}
      {todayCost && <div className={styles.row}><span className={styles.label}>{todayCost.total_input_tokens.toLocaleString()} in / {todayCost.total_output_tokens.toLocaleString()} out</span></div>}
      <button className={styles.toggle} onClick={() => setShow30day(!show30day)}>{show30day ? "▾" : "▸"} 30-day breakdown</button>
      {show30day && data && (
        <>
          <div className={styles.sectionLabel}>CONVERSATION COST (30 days)</div>
          <div className={styles.total}>${data.total_cost_usd.toFixed(6)}</div>
          <div className={styles.row}><span className={styles.label}>{data.total_input_tokens.toLocaleString()} in / {data.total_output_tokens.toLocaleString()} out tokens</span><span className={styles.skipped}>{data.total_skipped_calls} calls skipped</span></div>
          <div className={styles.barWrap}>
            {/* eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop */}
            {data.breakdown.map((b, i) => <span key={b.pipeline_key} className={styles.bar} style={{ width: `${Math.max(b.pct_of_total, 1)}%`, background: COLORS[i % COLORS.length] }} />)}
          </div>
          {data.breakdown.map((b, i) => (
            <div key={b.pipeline_key} className={styles.row}>
              {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
              <span className={styles.costName}><span className={styles.dot} style={{ background: COLORS[i % COLORS.length] }} />{_label(b.pipeline_key)}</span>
              <span className={styles.costMeta}>{b.call_count} calls · {b.pct_of_total}%</span>
            </div>
          ))}
        </>
      )}
      {show30day && !data && <div className={styles.emptyBanner}>No 30-day data yet.</div>}
    </div>
  );
}

function _label(key: string): string { return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()); }
