/** Per-message flow inspector backed by the conversation_inspector extension. */
import { useEffect, useState, useCallback } from "react";
import { useAdminCost } from "../../context/AdminCostContext";
import { fetchThreadFlow, type ConversationFlowResponse, type TurnData, type FlowStep } from "../../../../extensions/conversation_inspector/client/api";
import { STEP_STYLE } from "../../utils/pipelineStepStyle";
import aStyles from "./AdminShared.module.css";
import styles from "./MessageInspector.module.css";

interface InspectEvent { turnId?: number; callChainId?: string; timestamp?: string; }

function _sameSecond(a?: string, b?: string): boolean { if (!a || !b) return false; return a.slice(0, 19) === b.slice(0, 19) || a.slice(0, 16) === b.slice(0, 16); }
function _findTurn(flow: ConversationFlowResponse, ev: InspectEvent): TurnData | null {
  if (!ev.timestamp) return null;
  for (const turn of flow.turns) for (const step of turn.flow_steps) if ((step.type === "response" || step.type === "proactive_response") && _sameSecond(step.metadata?.timestamp as string, ev.timestamp)) return turn;
  return null;
}

function StepRow({ step }: { step: FlowStep }) {
  const [open, setOpen] = useState(false);
  const s = STEP_STYLE[step.type] || { color: "#8b8b8b", icon: "•" };
  const meta = step.metadata ?? {};
  const tokens: number = (meta.token_estimate as number) ?? 0;
  const hasDetail = (step.content?.length ?? 0) > 0 || Object.keys(meta).length > 0;

  return (
    <div className={styles.step}>
      {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
      <button onClick={() => setOpen((v) => !v)} className={hasDetail ? styles.stepBtnClickable : styles.stepBtnNoDetail} style={{ color: s.color }}>
        {hasDetail && <span className={styles.stepArrow}>{open ? "▼" : "▶"}</span>}
        <span>{s.icon} {step.label}</span>
        {tokens > 0 && <span className={styles.stepTokens}>~{tokens} tok</span>}
      </button>
      {open && hasDetail && (
        <div className={styles.stepDetail}>
          {step.content && <div>{step.content}</div>}
          {Object.keys(meta).length > 0 && (
            // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
            <div className={step.content ? styles.stepMeta : ""} style={{ borderTop: step.content ? undefined : "none", paddingTop: step.content ? undefined : 0 }}>
              {Object.entries(meta).filter(([k]) => k !== "full_text" && k !== "parts").map(([k, v]) => (
                <div key={k} className={styles.stepMetaItem}><span className={styles.stepMetaKey}>{k}:</span> {typeof v === "object" ? JSON.stringify(v) : String(v)}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function MessageInspector({ adminPanelOpen }: { adminPanelOpen: boolean }) {
  const { chatbotId } = useAdminCost();
  const [flow, setFlow] = useState<ConversationFlowResponse | null>(null);
  const [ev, setEv] = useState<InspectEvent | null>(null);
  const [loading, setLoading] = useState(false);
  const [flowError, setFlowError] = useState<string | null>(null);

  const loadFlow = useCallback(async (id: number) => { setLoading(true); setFlowError(null); try { setFlow(await fetchThreadFlow(id)); } catch { setFlowError("Could not load conversation flow."); } finally { setLoading(false); } }, []);

  useEffect(() => {
    if (!adminPanelOpen) { setEv(null); return; }
    const h = (e: Event) => { const ce = e as CustomEvent<InspectEvent>; setEv(ce.detail); if (chatbotId && !flow) loadFlow(chatbotId); };
    window.addEventListener("airunner:inspect-turn", h);
    return () => window.removeEventListener("airunner:inspect-turn", h);
  }, [adminPanelOpen, chatbotId, flow, loadFlow]);

  const turn = ev && flow ? _findTurn(flow, ev) : null;
  const totalTokens = turn ? turn.flow_steps.reduce((s, st) => s + ((st.metadata?.token_estimate as number) ?? 0), 0) : 0;

  return (
    <div className={aStyles.section}>
      <div className={aStyles.hdr}>MESSAGE INSPECTOR</div>
      {!ev && <div className={aStyles.mute}>Click any bot message to inspect its call chain.</div>}
      {ev && loading && <div className={aStyles.muteNormal}>Loading flow data…</div>}
      {ev && !loading && flowError && (
        <div className={styles.error}>{flowError}<button className={aStyles.reloadBtn} onClick={() => chatbotId && loadFlow(chatbotId)}>Retry</button></div>
      )}
      {ev && !loading && !flowError && !turn && flow && (
        <div className={aStyles.muteNormal}>
          <div>Turn not found in flow data.</div><div className={styles.notFound}>(Message may predate flow tracking. Try refreshing.)</div>
          <button className={aStyles.reloadBtn} onClick={() => chatbotId && loadFlow(chatbotId)}>Refresh flow</button>
        </div>
      )}
      {ev && !loading && !flowError && !flow && (
        <div className={aStyles.mute}><div>No flow data loaded.</div>{chatbotId && <button className={aStyles.reloadBtn} onClick={() => loadFlow(chatbotId)}>Load flow data</button>}</div>
      )}
      {turn && (
        <div>
          <div className={styles.turnHeader}>
            <div className={styles.turnLabel}>Turn {(turn as Record<string, unknown>).turn_index != null ? String((turn as Record<string, unknown>).turn_index as number + 1) : "?"}{(turn as Record<string, unknown>).is_proactive ? " · proactive" : ""}</div>
            <div className={styles.turnTokens}>~{totalTokens.toLocaleString()} tok</div>
          </div>
          <div>{turn.flow_steps.map((step, i) => <StepRow key={i} step={step} />)}</div>
          <button className={aStyles.reloadBtn} onClick={() => chatbotId && loadFlow(chatbotId)}>Refresh flow data</button>
        </div>
      )}
    </div>
  );
}
