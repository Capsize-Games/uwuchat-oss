/** Compact vertical conversation flow diagram. */
import type { PipelineStage, ConversationCostBreakdownItem } from "../../types/pipeline";
import aStyles from "./AdminShared.module.css";
import styles from "./ConversationFlow.module.css";

const CLR = ["#6c63ff","#4ade80","#f87171","#facc15","#38bdf8","#a78bfa","#fb923c","#2dd4bf","#f472b6","#94a3b8"];
const MSG = ["TOOL_CLASSIFICATION","DIALOGUE","NODE_VALIDATOR"];

interface Props { stages: PipelineStage[]; costBreakdown: ConversationCostBreakdownItem[]; }

export function ConversationFlow({ stages, costBreakdown }: Props) {
  const msgStages = stages.filter(s => MSG.includes(s.key));
  const bgStages = stages.filter(s => !MSG.includes(s.key));
  return (
    <div className={aStyles.sectionSm}>
      <div className={aStyles.hdrSmall}>CONVERSATION FLOW</div>
      <div className={styles.userNode}>👤 User sends message</div>
      <div className={styles.connectorSolid} />
      {msgStages.map((s, i) => <Node key={s.key} s={s} cost={costBreakdown.find(c => c.pipeline_key === s.key)} color={CLR[i % CLR.length]} last={false} />)}
      <div className={styles.connectorSolid} />
      <div className={styles.userNode}>✅ Response delivered</div>
      <div className={styles.connectorDashed} />
      <div className={styles.bgHeader}>
        <span className={styles.treePrefix}>├─</span>
        <span className={styles.bgLabel}>background</span>
      </div>
      {bgStages.slice(0, 5).map((s, i) => <Node key={s.key} s={s} cost={costBreakdown.find(c => c.pipeline_key === s.key)} color={CLR[(i + 3) % CLR.length]} indent last={false} />)}
      <Legend />
    </div>
  );
}

function Node({ s, cost, color, indent, last }: { s: PipelineStage; cost?: ConversationCostBreakdownItem; color: string; indent?: boolean; last: boolean }) {
  return (
    // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
    <div className={indent ? styles.nodeRowIndent : styles.nodeRow} style={{ opacity: s.enabled ? 1 : 0.4, textDecoration: s.enabled ? "none" : "line-through" }}>
      {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
      <div className={styles.dot} style={{ background: color }} />
      <span className={styles.nodeLabel}>{s.label}<span className={styles.nodeTrigger}>{s.trigger}</span></span>
      {cost ? <span className={styles.nodeCost}>${(cost.cost_usd * 30).toFixed(4)}/mo</span> : null}
    </div>
  );
}

function Legend() {
  return (
    <div className={styles.legend}>
      <div className={styles.legendTitle}>HOW THIS MAPS TO MESSAGE INSPECTOR</div>
      <div className={styles.legendText}>The <b className={styles.accentBold}>DIALOGUE</b> stage above encompasses everything you see in the message inspector:<br />&nbsp;&nbsp;💭 Thinking → 🔧 Tool calls → 📋 Tool results → 🤖 Assistant response<br />All of those are <b className={styles.accentBold}>one</b> DIALOGUE LLM call — one cost line item.</div>
      <div className={styles.legendNote}>⚙ System prompt = pre-built, cached (no LLM cost)<br />🔄 Per-turn context = datetime/mood/news (no LLM cost)<br />🎭 Background stages = fire-and-forget, independent of DIALOGUE</div>
    </div>
  );
}
