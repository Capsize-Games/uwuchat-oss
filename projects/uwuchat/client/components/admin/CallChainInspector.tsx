/** Per-message cost inspector — real dollar amounts from pipeline_token_usage. */
import { useEffect, useState, useCallback } from "react";
import { useAdminCost } from "../../context/AdminCostContext";
import type { CallChainDetail } from "../../types/pipeline";
import aStyles from "./AdminShared.module.css";
import styles from "./CallChainInspector.module.css";

interface InspectEvent { turnId?: number; callChainId?: string; timestamp?: string; }

const STEP_COLORS = ["#6c63ff", "#4ade80", "#f87171", "#facc15", "#38bdf8"];
const PIPELINE_LABELS: Record<string, string> = {
  DIALOGUE: "Dialogue", TOOL_CLASSIFICATION: "Tool Class", MOOD_TRACKER: "Mood",
  NEWS_SYNTHESIS: "News", KNOWLEDGE_EXTRACTION: "Knowledge", NODE_VALIDATOR: "Validator", STATELESS: "Stateless",
};
function _label(key: string): string { return PIPELINE_LABELS[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()); }

export function CallChainInspector({ adminPanelOpen }: { adminPanelOpen: boolean }) {
  const { getCallChain } = useAdminCost();
  const [chain, setChain] = useState<CallChainDetail | null>(null);
  const [ev, setEv] = useState<InspectEvent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadChain = useCallback(async (callChainId: string) => { setLoading(true); setError(null); try { setChain(await getCallChain(callChainId)); } catch { setError("Could not load call chain."); } finally { setLoading(false); } }, [getCallChain]);

  useEffect(() => {
    if (!adminPanelOpen) { setEv(null); setChain(null); return; }
    const h = (e: Event) => { const d = (e as CustomEvent<InspectEvent>).detail; setEv(d); setChain(null); setError(null); if (d.callChainId) loadChain(d.callChainId); };
    window.addEventListener("airunner:inspect-turn", h);
    return () => window.removeEventListener("airunner:inspect-turn", h);
  }, [adminPanelOpen, loadChain]);

  return (
    <div className={aStyles.section}>
      <div className={aStyles.hdr}>COST BREAKDOWN</div>
      {!ev && <div className={aStyles.mute}>Click a bot message to see its cost breakdown.</div>}
      {ev && loading && <div className={aStyles.muteNormal}>Loading cost data…</div>}
      {ev && !loading && error && <div className={styles.error}>{error}{ev.callChainId && <button className={aStyles.reloadBtn} onClick={() => loadChain(ev.callChainId!)}>Retry</button>}</div>}
      {ev && !loading && !error && !ev.callChainId && <div className={aStyles.mute}>No call chain data for this message (pre-tracking).</div>}
      {chain && (
        <div>
          <div className={styles.summaryRow}>
            <div className={styles.summaryLabel}>{chain.steps.length} pipeline stage{chain.steps.length !== 1 ? "s" : ""}</div>
            <div className={styles.summaryCost}>~${chain.total_cost_usd.toFixed(6)} total</div>
          </div>
          <div className={styles.tokenInfo}>{chain.total_input_tokens.toLocaleString()} in / {chain.total_output_tokens.toLocaleString()} out tokens</div>
          {chain.steps.map((step, i) => (
            // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
            <div key={i} className={styles.stepRow} style={{ opacity: step.skipped ? 0.4 : 1 }}>
              <div className={styles.stepHeader}>
                {/* eslint-disable-next-line no-restricted-syntax -- lookup-table color from shared constants */}
                <div className={styles.dot} style={{ background: STEP_COLORS[i % STEP_COLORS.length] }} />
                <span className={styles.stepName}>{_label(step.pipeline_key)}{step.skipped && <span className={styles.skippedTag}>skipped</span>}</span>
                <span className={styles.stepCost}>${step.cost_usd.toFixed(6)}</span>
              </div>
              <div className={styles.stepMeta}>
                <span className={styles.stepModel}>{step.model_id}</span> · {step.input_tokens.toLocaleString()} in / {step.output_tokens.toLocaleString()} out
                {step.tier_name && <span className={styles.tierName}>· {step.tier_name}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
