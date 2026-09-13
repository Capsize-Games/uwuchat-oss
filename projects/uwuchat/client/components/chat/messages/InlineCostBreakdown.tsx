/** Inline cost breakdown shown after bot messages in admin mode. */

import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { createPortal } from "react-dom";
import { useAuth } from "../../../hooks/useAuth";
import { useAdminCost } from "../../../context/AdminCostContext";
import type { CallChainDetail, CallChainStep } from "../../../types/pipeline";
import styles from "./InlineCostBreakdown.module.css";

interface Props {
  callChainId: string | null | undefined;
}

function stageDesc(key: string): string {
  if (key.startsWith("DIALOGUE (tool call)")) return "The LLM decided to invoke tools. It generates the tool name and arguments.";
  if (key.startsWith("DIALOGUE (response)")) return "The LLM produces the visible chat response. May include tool results injected into the prompt.";
  const M: Record<string, string> = {
    INTRA_SESSION_MOOD: "Updates mood and emoji from recent conversation (cheap model, every few turns).",
    TOOL_CLASSIFICATION: "Classifies available tools for this turn.",
    NODE_VALIDATOR: "Validates response against character rules and safety.",
    SUMMARIZATION: "Generates LLM summary of an article or URL.",
    NEWS_SYNTHESIS: "Synthesizes news articles into a daily digest.",
    KNOWLEDGE_EXTRACTION: "Extracts facts for long-term memory.",
    STATELESS: "One-shot LLM call (no conversation context).",
  };
  return M[key] || "";
}

function pLabel(key: string): string {
  if (key.startsWith("DIALOGUE (tool call)")) return "🛠 Tool call";
  if (key.startsWith("DIALOGUE (response)")) return "💬 Response";
  const MAP: Record<string, string> = {
    DIALOGUE: "💬 Dialogue", TOOL_CLASSIFICATION: "🔧 Tool Class",
    INTRA_SESSION_MOOD: "🎭 Mood", MOOD_TRACKER: "🎭 Mood",
    SUMMARIZATION: "📝 Summary", NEWS_SYNTHESIS: "📰 News",
    KNOWLEDGE_EXTRACTION: "🧠 Knowledge", NODE_VALIDATOR: "✅ Validator",
    STATELESS: "⚡ Stateless",
  };
  return MAP[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function getAuthHeader(accessToken: string | null): Record<string, string> {
  if (accessToken) return { Authorization: `Bearer ${accessToken}` };
  return {};
}

async function fetchCallChain(
  cid: string,
  accessToken: string | null,
): Promise<CallChainDetail | null> {
  const headers = getAuthHeader(accessToken);
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const resp = await fetch(`/api/v1/admin/call-chain/${cid}`, { headers });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch {
      if (attempt < 2) await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
    }
  }
  return null;
}

function StepRow({ step, t }: { step: CallChainStep; t: (key: string) => string }) {
  const [modal, setModal] = useState(false);

  return (
    <>
      <tr
        className={styles.row}
        // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
        style={{ opacity: step.skipped ? 0.35 : 1 }}
        onClick={() => setModal(true)}
      >
        <td className={styles.cell}>{pLabel(step.pipeline_key)}</td>
        <td className={styles.cellMono}>{step.model_id}</td>
        <td className={styles.cellRightMono}>{step.input_tokens.toLocaleString()}</td>
        <td className={styles.cellRightMono}>{step.output_tokens.toLocaleString()}</td>
        <td className={step.cost_usd > 0 ? styles.costGreen : styles.costMuted}>
          ${step.cost_usd.toFixed(6)}
        </td>
      </tr>
      {modal && createPortal(
        <div className={styles.modalOverlay} onClick={() => setModal(false)}>
          <div className={styles.modalBox} onClick={(e) => e.stopPropagation()}>
            <div className={styles.modalTitle}>{pLabel(step.pipeline_key)}</div>
            <div className={styles.modalDesc}>{stageDesc(step.pipeline_key)}</div>
            <table className={styles.modalTable}>
              <tbody>
                <tr><td className={styles.modalK}>Model</td><td className={styles.modalV}>{step.model_id}</td></tr>
                <tr><td className={styles.modalK}>Input tokens</td><td className={styles.modalV}>{step.input_tokens.toLocaleString()}</td></tr>
                <tr><td className={styles.modalK}>Output tokens</td><td className={styles.modalV}>{step.output_tokens.toLocaleString()}</td></tr>
                <tr><td className={styles.modalK}>Cost</td><td className={styles.modalVCost}>${step.cost_usd.toFixed(8)}</td></tr>
                {step.cache_read_tokens > 0 && (
                  <tr><td className={styles.modalK}>Cache read</td><td className={styles.modalV}>{step.cache_read_tokens.toLocaleString()} tokens</td></tr>
                )}
                {step.tier_name && (
                  <tr><td className={styles.modalK}>Tier</td><td className={styles.modalV}>{step.tier_name}</td></tr>
                )}
                {step.complexity_score != null && (
                  <tr><td className={styles.modalK}>Complexity</td><td className={styles.modalV}>{step.complexity_score.toFixed(2)}</td></tr>
                )}
                {step.skipped && (
                  <tr><td className={styles.modalK}>Status</td><td className={`${styles.modalV} ${styles.statusSkipped}`}>Skipped</td></tr>
                )}
                {step.recorded_at && (
                  <tr><td className={styles.modalK}>Timestamp</td><td className={styles.modalV}>{new Date(step.recorded_at).toLocaleString()}</td></tr>
                )}
              </tbody>
            </table>
            {step.prompt_char_count != null && (
              <div className={styles.modalSection}>
                <div className={styles.modalSectionHdr}>{t("chat.view.input_prompt")}</div>
                <div className={styles.modalMeta}>{step.prompt_char_count.toLocaleString()} characters</div>
              </div>
            )}
            {step.response_char_count != null && (
              <div className={styles.modalSection}>
                <div className={styles.modalSectionHdr}>{t("chat.view.output_response")}</div>
                <div className={styles.modalMeta}>{step.response_char_count.toLocaleString()} characters</div>
              </div>
            )}
            <button className={styles.modalClose} onClick={() => setModal(false)}>{t("common.close")}</button>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}

export function InlineCostBreakdown({ callChainId }: Props) {
  const { t } = useTranslation();
  const { isSuperuser } = useAdminCost();
  const { accessToken } = useAuth();
  const [chain, setChain] = useState<CallChainDetail | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    if (!callChainId) return;
    const result = await fetchCallChain(callChainId, accessToken);
    if (result) setChain(result);
    else setError(true);
  }, [callChainId, accessToken]);

  useEffect(() => { setChain(null); setError(false); if (callChainId) load(); }, [callChainId, load]);

  if (!isSuperuser || !callChainId) return null;

  if (error) return <div className={styles.stateMsg}>Cost fetch failed for {callChainId.slice(0, 8)}…</div>;
  if (!chain) return <div className={styles.stateMsg}>Loading cost… {callChainId.slice(0, 8)}…</div>;
  if (chain.steps.length === 0) return <div className={styles.stateMsg}>No cost data for {callChainId.slice(0, 8)}…</div>;

  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <thead>
          <tr className={styles.hdrRow}>
            <th className={styles.hdrCell}>Stage</th>
            <th className={styles.hdrCell}>Model</th>
            <th className={styles.hdrCellRight}>In</th>
            <th className={styles.hdrCellRight}>Out</th>
            <th className={styles.hdrCellRight}>Cost</th>
          </tr>
        </thead>
        <tbody>
          {chain.steps.map((step) => (
            <StepRow key={`${step.pipeline_key}-${step.sequence}`} step={step} t={t} />
          ))}
        </tbody>
        <tfoot>
          <tr className={styles.footerRow}>
            <td className={styles.footerCell} colSpan={2}>{chain.steps.length} stage{chain.steps.length !== 1 ? "s" : ""}</td>
            <td className={styles.footerCellRight}>{chain.total_input_tokens.toLocaleString()}</td>
            <td className={styles.footerCellRight}>{chain.total_output_tokens.toLocaleString()}</td>
            <td className={chain.total_cost_usd > 0 ? styles.footerCostGreen : styles.footerCostMuted}>
              ${chain.total_cost_usd.toFixed(6)}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
