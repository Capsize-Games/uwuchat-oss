/**
 * Flow detail panel — shows full details of a flow step in the right sidebar.
 * Displays all data recursively as key/value pairs with bold key headers.
 * Nested objects are expanded inline as sub-keys.
 */
import { useState, useCallback } from "react";
import type { FlowStep } from "@extensions/conversation_inspector/client/api";
import type { CallChainStep } from "../../types/pipeline";
import { pipelineStageInfo } from "./messages/pipelineStageInfo";
import { STEP_STYLE } from "../../utils/pipelineStepStyle";
import styles from "./FlowDetailPanel.module.css";

interface Props {
  step: FlowStep;
  costStep?: CallChainStep;
}


function titleCase(k: string): string {
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function isCostKey(k: string): boolean {
  return k.toLowerCase().includes("cost") || k === "cost usd";
}

function tryParseJson(v: unknown): unknown {
  if (typeof v !== "string") return v;
  try {
    const parsed = JSON.parse(v);
    if (typeof parsed === "object" && parsed !== null) return parsed;
  } catch { /* not JSON */ }
  return v;
}

/**
 * Copy button shown on long-text content blocks.  Fades "Copied!"
 * feedback after a brief timeout.
 */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    }).catch(() => {
      // Clipboard API unavailable — silently ignore.
    });
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      title={copied ? "Copied!" : "Copy to clipboard"}
      className={styles.copyBtn}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        background: copied
          ? "rgba(var(--theme-success-rgb), 0.15)"
          : "rgba(255,255,255,0.06)",
        color: copied ? "var(--theme-success)" : "rgba(255,255,255,0.4)",
      }}
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

/**
 * Render a single primitive key/value pair with a copy button
 * on long (>40 char) string values.
 */
function StringValue({ k, v }: { k: string; v: unknown }) {
  const isLong = typeof v === "string" && (v as string).length > 40;
  const displayText =
    isCostKey(k) && typeof v === "number"
      ? `$${v.toFixed(8)}`
      : typeof v === "number"
      ? v.toLocaleString()
      : String(v);

  return (
    <div
      className={`${styles.stringValue} ${isLong ? styles.stringValueLong : ""} ${isCostKey(k) ? styles.costValue : ""}`}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        fontSize: isLong ? 10 : 12,
        padding: isLong ? undefined : 0,
      }}
    >
      {displayText}
      {isLong && <CopyButton text={displayText} />}
    </div>
  );
}

/**
 * Recursively render a value. If it's an object, show its keys as
 * nested key/value pairs. Strings over 40 chars get monospace blocks.
 */
function ValueDisplay({ value, depth = 0 }: { value: unknown; depth?: number }) {
  const resolved = tryParseJson(value);

  if (Array.isArray(resolved)) {
    return (
      <div className={depth > 0 ? styles.nestedValue : ""}>
        {resolved.map((item, i) => (
          <div key={i} className={styles.arrayItem}>
            <div className={styles.arrayIndex}>
              [{i}]
            </div>
            <ValueDisplay value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }

  if (isObj(resolved)) {
    return (
      <div
        className={styles.objValue}
        // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
        style={{
          borderLeft: depth > 0 ? "1px solid rgba(255,255,255,0.08)" : "none",
          marginBottom: depth === 0 ? 4 : 2,
        }}
      >
        {Object.entries(resolved).map(([k, v]) => (
          <div key={k} className={styles.objEntry}>
            <div className={styles.objKey}>
              {titleCase(k)}
            </div>
            {isObj(v) || Array.isArray(v) ? (
              <ValueDisplay value={v} depth={depth + 1} />
            ) : (
              <StringValue k={k} v={v} />
            )}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={styles.primitiveValue}>
      {String(value)}
    </div>
  );
}

export default function FlowDetailPanel({ step, costStep }: Props) {
  const style = STEP_STYLE[step.type] || { color: "#8b8b8b", icon: "•" };
  const meta = step.metadata as Record<string, unknown> | null;

  let data: Record<string, unknown> = {};

  if (step.content) {
    try {
      const parsed = JSON.parse(step.content);
      if (
        typeof parsed === "object" &&
        parsed !== null &&
        !Array.isArray(parsed)
      ) {
        data = { ...data, ...(parsed as Record<string, unknown>) };
      }
    } catch {
      if (!meta?.arguments) {
        data["Content"] = step.content;
      }
    }
  }

  if (meta) {
    data = { ...data, ...meta };
  }

  if (costStep) {
    if (costStep.model_id) data["model"] = costStep.model_id;
    if (costStep.cost_usd != null) data["cost_usd"] = costStep.cost_usd;
    if (costStep.input_tokens != null) {
      data["input_tokens"] = costStep.input_tokens;
    }
    if (costStep.output_tokens != null) {
      data["output_tokens"] = costStep.output_tokens;
    }
    if (costStep.prompt_char_count != null) {
      data["prompt_chars"] = costStep.prompt_char_count;
    }
    if (costStep.response_char_count != null) {
      data["response_chars"] = costStep.response_char_count;
    }
  }

  const { pipeline_key: _, ...restData } = data;

  // Extract prompt context from metadata for a dedicated section.
  const spFullText =
    typeof meta?.system_prompt_full_text === "string"
      ? (meta.system_prompt_full_text as string)
      : "";
  const ptcFullText =
    typeof meta?.per_turn_context_full_text === "string"
      ? (meta.per_turn_context_full_text as string)
      : "";
  const showPromptContext =
    (spFullText || ptcFullText) &&
    (step.type === "thinking" || step.type === "response");
  const [promptExpanded, setPromptExpanded] = useState(false);

  return (
    <div className={styles.wrapper}>
      <div className={styles.panelLabel}>
        Flow Step Detail
      </div>

      <div className={styles.typeHeader}>
        <span className={styles.typeIcon}>{style.icon}</span>
        {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
        <span className={styles.typeLabel} style={{ color: style.color }}>
          {step.label}
        </span>
      </div>

      {showPromptContext && (
        <div
          className={styles.promptSection}
          // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
          style={{ paddingBottom: promptExpanded ? 12 : 0 }}
        >
          <button
            onClick={() => setPromptExpanded((p) => !p)}
            className={styles.promptToggle}
            // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
            style={{ marginBottom: promptExpanded ? 8 : 0 }}
          >
            <span>
              {promptExpanded ? "▼" : "▶"}{" "}
              System Prompt / Context Used
            </span>
            <span className={styles.promptToggleInfo}>
              ({spFullText ? `${spFullText.length.toLocaleString()} chars` : ""}
              {spFullText && ptcFullText ? " + " : ""}
              {ptcFullText ? `${ptcFullText.length.toLocaleString()} chars context` : ""})
            </span>
          </button>
          {promptExpanded && (
            <div className={styles.promptExpanded}>
              {spFullText && (
                <div className={styles.promptBlock}>
                  <div className={styles.promptBlockLabel}>
                    System Prompt
                  </div>
                  <div className={styles.promptBlockContent}>
                    {spFullText}
                    <CopyButton text={spFullText} />
                  </div>
                </div>
              )}
              {ptcFullText && (
                <div>
                  <div className={styles.promptBlockLabel}>
                    Per-Turn Context
                  </div>
                  <div className={styles.promptBlockContent}>
                    {ptcFullText}
                    <CopyButton text={ptcFullText} />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {Object.keys(data).length === 0 && (
        <div className={styles.emptyState}>
          No data available for this step.
        </div>
      )}

      {data["pipeline_key"] && (
        <div className={styles.pipelineSection}>
          <div className={styles.pipelineLabel}>
            Pipeline Stage
          </div>
          {(() => {
            const info = pipelineStageInfo(
              String(data["pipeline_key"]),
            );
            return (
              <>
                <div className={styles.pipelineName}>
                  {info.label}
                </div>
                <div className={styles.pipelineDesc}>
                  {info.description}
                </div>
              </>
            );
          })()}
        </div>
      )}

      <ValueDisplay value={restData} />
    </div>
  );
}
