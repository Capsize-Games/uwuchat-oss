/** Pipeline flow diagram — per-message call chain or aggregate conversation costs. */

import { useState } from "react";
import type { CallChainDetail, CallChainStep, ConversationCostBreakdownItem } from "../../types/pipeline";
import styles from "./PipelineFlowDiagram.module.css";

const CLR: Record<string, string> = {
  dialogue: "#6c63ff", classification: "#facc15", validator: "#4ade80",
  mood: "#eb459e", curiosity: "#faa61a", compressor: "#38bdf8",
  summarizer: "#fb923c", memory: "#a78bfa", world: "#2dd4bf",
  stateless: "#94a3b8",
};

function _color(key: string): string {
  const k = key.toLowerCase();
  for (const [kw, c] of Object.entries(CLR)) {
    if (k === kw || k.includes(kw)) return c;
  }
  return "#64748b";
}

function _label(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function _icon(key: string): string {
  const k = key.toLowerCase();
  if (k === "dialogue") return "💬";
  if (k.includes("tool_class")) return "🧠";
  if (k.includes("node_valid")) return "✅";
  if (k.includes("mood")) return "🎭";
  if (k.includes("curiosity")) return "🔍";
  if (k.includes("compress")) return "📦";
  if (k.includes("summariz")) return "📝";
  if (k.includes("memory")) return "🧩";
  if (k.includes("world")) return "🌍";
  if (k.includes("stateless")) return "⚡";
  return "⚙";
}

interface Props {
  callChain: CallChainDetail | null;
  fallbackBreakdown: ConversationCostBreakdownItem[];
}

export function PipelineFlowDiagram({ callChain, fallbackBreakdown }: Props) {
  // Per-message call chain
  if (callChain && callChain.steps.length > 0) {
    const steps = callChain.steps.filter(s => !s.skipped);
    return (
      <div className={styles.full}>
        <div className={styles.header}>PIPELINE FLOW · this message</div>
        <div className={styles.summary}>
          <span className={styles.summaryCost}>
            ${callChain.total_cost_usd.toFixed(6)}
          </span>
          <span className={styles.muted}>
            {callChain.total_input_tokens.toLocaleString()} in / {callChain.total_output_tokens.toLocaleString()} out
          </span>
          <span className={styles.faint}>{steps.length} calls</span>
        </div>
        <div className={styles.scroll}>
          {steps.map(s => <StepNode key={`${s.pipeline_key}-${s.sequence}`} step={s} />)}
        </div>
      </div>
    );
  }

  // Fallback: aggregate conversation costs
  if (fallbackBreakdown.length > 0) {
    return (
      <div className={styles.full}>
        <div className={styles.header}>PIPELINE FLOW · all messages</div>
        <div className={`${styles.summary} ${styles.aggregateBanner}`}>
          <span className={styles.aggregateText}>
            Aggregate costs across all messages. Click Inspect Flow on a new message for per-message breakdown.
          </span>
        </div>
        <div className={styles.scroll}>
          {fallbackBreakdown.map(b => {
            const clr = _color(b.pipeline_key);
            return (
              <div
                key={`${b.pipeline_key}-${b.model_id}`}
                className={styles.aggRow}
                // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                style={{
                  background: `linear-gradient(135deg, ${clr}12, ${clr}06)`,
                  border: `1px solid ${clr}28`,
                }}
              >
                <div className={styles.aggRowInner}>
                  <span className={styles.aggIcon}>{_icon(b.pipeline_key)}</span>
                  <span className={styles.aggLabel}>{_label(b.pipeline_key)}</span>
                  <span className={b.cost_usd > 0 ? styles.costGreen : styles.costZero}>
                    {b.cost_usd > 0 ? `$${b.cost_usd.toFixed(6)}` : "$0"}
                  </span>
                </div>
                <div className={styles.aggMeta}>
                  <span className={styles.stepMetaModel}>{b.model_id}</span>
                  <span className={styles.stepMetaTokens}>
                    {b.input_tokens.toLocaleString()} in / {b.output_tokens.toLocaleString()} out
                  </span>
                  <span className={styles.stepMetaCalls}>{b.call_count} calls</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // No data at all
  return (
    <div className={styles.sFull}>
      <div className={styles.sHeader}>PIPELINE FLOW</div>
      <div className={styles.sEmpty}>
        <div>
          <div className={styles.emptyMsg}>Click a message's "Inspect Flow" button</div>
          <div className={styles.emptyHint}>Or send messages to build up aggregate costs</div>
        </div>
      </div>
    </div>
  );
}

function StepNode({ step }: { step: CallChainStep }) {
  const [hovered, setHovered] = useState(false);
  const color = _color(step.pipeline_key);
  return (
    <div
      className={styles.stepNode}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        background: `linear-gradient(135deg, ${color}12, ${color}06)`,
        border: `1px solid ${hovered ? `${color}70` : `${color}28`}`,
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className={styles.stepNodeInner}>
        <span className={styles.stepIcon}>{_icon(step.pipeline_key)}</span>
        <span className={styles.stepLabelText}>{_label(step.pipeline_key)}</span>
        {step.tier_name && <span className={styles.stepBadge}>{step.tier_name}</span>}
        <span className={step.cost_usd > 0 ? styles.costGreen : styles.costZero}>
          {step.cost_usd > 0 ? `$${step.cost_usd.toFixed(6)}` : "$0"}
        </span>
      </div>
      <div className={styles.stepMeta}>
        <span className={styles.stepMetaModel}>{step.model_id}</span>
        <span className={styles.stepMetaTokens}>
          {step.input_tokens.toLocaleString()} in / {step.output_tokens.toLocaleString()} out
          {step.cache_read_tokens > 0 ? ` · ${step.cache_read_tokens.toLocaleString()} cache` : ""}
        </span>
      </div>
    </div>
  );
}
