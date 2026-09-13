/**
 * Inline flow visualization for a single conversation turn.
 * Shows system prompt, context, user message, tool calls, tool results,
 * and response as connected nodes in the message thread.
 */
import { useState } from "react";
import type {
  TurnData,
  FlowStep,
} from "@extensions/conversation_inspector/client/api";
import { STEP_STYLE } from "../../../utils/pipelineStepStyle";
import styles from "./TurnFlowView.module.css";

interface Props {
  turn: TurnData;
  turnNumber: number;
}

export default function TurnFlowView({ turn, turnNumber }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());

  const toggleStep = (i: number) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  const toolCount = turn.flow_steps.filter(
    (s) => s.type === "tool_call" || s.type === "tool_result",
  ).length;
  const userText =
    turn.user_message && typeof turn.user_message === "object"
      ? String(
          (turn.user_message as Record<string, unknown>).content || "",
        ).slice(0, 60)
      : "";
  const totalToks = Math.round(turn.total_characters / 4);

  const headerClass = expanded
    ? `${styles.turnHeader} ${styles.turnHeaderExpanded}`
    : styles.turnHeader;

  return (
    <div className={styles.turnCard}>
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={headerClass}
      >
        <span className={styles.turnArrow}>
          {expanded ? "▼" : "▶"}
        </span>
        Turn {turnNumber}
        {userText && (
          <span className={styles.turnUserText}>
            "{userText}{userText.length >= 60 ? "…" : ""}"
          </span>
        )}
        <span className={styles.turnMeta}>
          {toolCount > 0 && `${toolCount} tools · `}
          {totalToks} tok
        </span>
      </button>

      {/* Flow steps */}
      {expanded && (
        <div className={styles.stepsWrap}>
          <div className={styles.stepsInner}>
            {turn.flow_steps.map((step, i) => {
              const isLast = i === turn.flow_steps.length - 1;
              const stepExpanded = expandedSteps.has(i);
              return (
                <FlowStepRow
                  key={i}
                  step={step}
                  isLast={isLast}
                  expanded={stepExpanded}
                  onToggle={() => toggleStep(i)}
                />
              );
            })}
            {turn.flow_steps.length === 0 && (
              <div className={styles.emptyState}>
                No flow steps recorded for this turn.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Single flow step row with connector ── */

function FlowStepRow({
  step,
  isLast,
  expanded,
  onToggle,
}: {
  step: FlowStep;
  isLast: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const style = STEP_STYLE[step.type] || { color: "#8b8b8b", icon: "•" };
  const hasDetail =
    (step.content?.length ?? 0) > 0 ||
    (step.metadata && Object.keys(step.metadata).length > 0);

  const btnCursorClass = hasDetail
    ? styles.stepBtnClickable
    : styles.stepBtnNoCursor;

  return (
    <div
      className={styles.stepRow}
      // eslint-disable-next-line no-restricted-syntax -- state-driven conditional style
      style={{ minHeight: isLast ? 20 : undefined }}
    >
      {/* Connector column */}
      <div className={styles.stepConnector}>
        <div
          className={styles.stepDot}
          // eslint-disable-next-line no-restricted-syntax -- CSS custom property for pipeline color
          style={{ "--step-color": style.color } as React.CSSProperties}
        />
        {!isLast && <div className={styles.stepLine} />}
      </div>

      {/* Content */}
      <div
        className={styles.stepBody}
        // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
        style={{
          "--step-pb": isLast ? "0px" : "4px",
        } as React.CSSProperties}
      >
        <button
          onClick={onToggle}
          className={`${styles.stepBtn} ${btnCursorClass}`}
          // eslint-disable-next-line no-restricted-syntax -- CSS custom property for pipeline color
          style={{ "--step-color": style.color } as React.CSSProperties}
        >
          {hasDetail && (
            <span className={styles.stepExpandIcon}>
              {expanded ? "▼" : "▶"}
            </span>
          )}
          <span
            className={styles.stepLabel}
            // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
            style={{
              "--step-label-opacity": hasDetail ? 1 : 0.6,
            } as React.CSSProperties}
          >
            {style.icon} {step.label}
          </span>
          {!hasDetail && step.content && (
            <span className={styles.stepPreview}>
              {step.content.slice(0, 50)}
            </span>
          )}
        </button>

        {expanded && hasDetail && (
          <div className={styles.stepDetail}>
            {step.content}
            {step.metadata && Object.keys(step.metadata).length > 0 && (
              <div className={styles.stepMeta}>
                {Object.entries(step.metadata).map(([k, v]) => {
                  const val =
                    typeof v === "object"
                      ? JSON.stringify(v, null, 2)
                      : String(v);
                  return (
                    <div key={k} className={styles.stepMetaItem}>
                      <span className={styles.stepMetaKey}>{k}:</span> {val}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
