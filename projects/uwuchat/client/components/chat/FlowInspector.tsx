import { useState, useCallback, useEffect } from "react";
import { fetchThreadFlow, type ConversationFlowResponse, type TurnData, type FlowStep } from "../../../../extensions/conversation_inspector/client/api";
import { STEP_STYLE } from "../../utils/pipelineStepStyle";
import styles from "./FlowInspector.module.css";

interface FlowInspectorProps {
  chatbotId: number;
  onClose: () => void;
}

export default function FlowInspector({ chatbotId, onClose }: FlowInspectorProps) {
  const [flow, setFlow] = useState<ConversationFlowResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedTurns, setExpandedTurns] = useState<Set<number>>(new Set());
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchThreadFlow(chatbotId);
      setFlow(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch flow");
    } finally {
      setLoading(false);
    }
  }, [chatbotId]);

  useEffect(() => { fetch(); }, [fetch]);

  const toggleTurn = (index: number) => {
    setExpandedTurns((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const toggleStep = (key: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const stepKey = (turnIdx: number, stepIdx: number) => `${turnIdx}-${stepIdx}`;

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <span className={styles.headerTitle}>
          🔍 Conversation Flow
          {flow && (
            <span className={styles.headerCount}>
              ({flow.turns.length} turns)
            </span>
          )}
        </span>
        <span className={styles.headerActions}>
          <button
            onClick={fetch}
            disabled={loading}
            className={styles.refreshBtn}
          >
            {loading ? "..." : "🔄"}
          </button>
          <button
            onClick={onClose}
            className={styles.closeBtn}
          >
            ×
          </button>
        </span>
      </div>

      <div className={styles.scrollArea}>
        {loading && (
          <div className={styles.centerMsg}>
            Loading flow data...
          </div>
        )}
        {error && (
          <div className={styles.errorMsg}>
            {error}
          </div>
        )}
        {flow && flow.turns.length === 0 && (
          <div className={styles.centerMsg}>
            No conversation turns yet.
          </div>
        )}
        {flow && flow.turns.map((turn, ti) => (
          <TurnCard
            key={ti}
            turn={turn}
            turnIndex={ti}
            expanded={expandedTurns.has(ti)}
            expandedSteps={expandedSteps}
            onToggleTurn={() => toggleTurn(ti)}
            onToggleStep={(si) => toggleStep(stepKey(ti, si))}
            stepKeyFn={(si) => stepKey(ti, si)}
          />
        ))}
      </div>
    </div>
  );
}

function TurnCard({
  turn,
  turnIndex,
  expanded,
  expandedSteps,
  onToggleTurn,
  onToggleStep,
  stepKeyFn,
}: {
  turn: TurnData;
  turnIndex: number;
  expanded: boolean;
  expandedSteps: Set<string>;
  onToggleTurn: () => void;
  onToggleStep: (si: number) => void;
  stepKeyFn: (si: number) => string;
}) {
  const toolCount = turn.flow_steps.filter(
    (s) => s.type === "tool_call" || s.type === "tool_result",
  ).length;
  const userText = turn.user_message && typeof turn.user_message === "object"
    ? String((turn.user_message as Record<string, unknown>).content || "").slice(0, 60)
    : "";
  const convId = (turn as Record<string, unknown>).conv_id;

  return (
    <div className={styles.turnCard}>
      <button
        onClick={onToggleTurn}
        className={styles.turnBtn}
      >
        <span className={styles.turnArrow}>{expanded ? "▼" : "▶"}</span>
        Turn {turnIndex + 1}
        {userText && (
          <span className={styles.turnUserText}>
            &ldquo;{userText}{userText.length >= 60 ? "…" : ""}&rdquo;
          </span>
        )}
        <span className={styles.turnMeta}>
          {toolCount > 0 && `${toolCount} tools · `}
          {Math.round(turn.total_characters / 4)} tok
          {convId != null && ` · conv #${convId}`}
        </span>
      </button>
      {expanded && (
        <div className={styles.turnSteps}>
          {turn.flow_steps.map((step, si) => {
            const key = stepKeyFn(si);
            const isExpanded = expandedSteps.has(key);
            return (
              <StepRow
                key={si}
                step={step}
                expanded={isExpanded}
                onToggle={() => onToggleStep(si)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function StepRow({
  step,
  expanded,
  onToggle,
}: {
  step: FlowStep;
  expanded: boolean;
  onToggle: () => void;
}) {
  const style = STEP_STYLE[step.type] || { color: "#8b8b8b", icon: "•" };
  const hasDetail = (step.content?.length ?? 0) > 0
    || (step.metadata && Object.keys(step.metadata).length > 0);

  return (
    <div>
      <button
        onClick={onToggle}
        className={styles.stepRow}
        // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
        style={{ color: style.color }}
      >
        {hasDetail && (
          <span className={styles.stepArrow}>{expanded ? "▼" : "▶"}</span>
        )}
        <span className={hasDetail ? styles.stepLabel : styles.stepLabelDim}>
          {style.icon} {step.label}
        </span>
        {!hasDetail && step.content && (
          <span className={styles.stepContentInline}>
            {step.content.slice(0, 60)}
          </span>
        )}
      </button>
      {expanded && hasDetail && (
        <div className={styles.stepDetail}>
          {step.content}
          {step.metadata && Object.keys(step.metadata).length > 0 && (
            <div className={styles.stepMeta}>
              {Object.entries(step.metadata).map(([k, v]) => {
                const val = typeof v === "object" ? JSON.stringify(v, null, 2) : String(v);
                return (
                  <div key={k} className={styles.stepMetaRow}>
                    <span className={styles.stepMetaKey}>{k}:</span> {val}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
