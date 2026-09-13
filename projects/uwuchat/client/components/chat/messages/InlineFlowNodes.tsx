/**
 * Inline flow nodes rendered between user and assistant messages
 * when inspection mode is enabled. Shows tool calls, tool results,
 * and other flow steps as clickable connected nodes.
 *
 * Clicking a node opens its full detail in the right sidebar panel.
 */
import type { FlowStep } from "@extensions/conversation_inspector/client/api";
import { pipelineStageInfo } from "./pipelineStageInfo";
import { STEP_STYLE } from "../../../utils/pipelineStepStyle";
import styles from "./InlineFlowNodes.module.css";

import type { CallChainDetail } from "../../../types/pipeline";

interface Props {
  steps: FlowStep[];
  /** "pre" = before user message (system_prompt, per_turn_context).
   *  "mid" = between user and assistant (tool_call, tool_result, etc.) */
  position: "pre" | "mid";
  /** CallChainDetail for this turn (cost/token data from pipeline API) */
  costDetail?: CallChainDetail | null;
}

const PRE_TYPES = new Set(["system_prompt", "per_turn_context", "semantic_bridge"]);

/** Categories that run as separately-billed pipeline calls.
 *  system/math/research/search → TOOL_EXECUTION
 *  knowledge → KNOWLEDGE (async extractor)
 *  mood/conversation → inline within DIALOGUE (no separate cost row) */
const _SEPARATELY_BILLED: Record<string, string> = {
  system: "TOOL_EXECUTION",
  math: "TOOL_EXECUTION",
  research: "TOOL_EXECUTION",
  search: "TOOL_EXECUTION",
  knowledge: "KNOWLEDGE",
};

/** Resolve a flow step to the pipeline_key it should match against.
 *  tool_call steps return a fully-qualified key with "(tool call)"
 *  suffix so they pair with the correct cost row even when the same
 *  category also has "(response)" rows. */
function _resolveTarget(step: FlowStep): string {
  if (step.type === "mood_update") return "MOOD";
  if (step.type === "rag_step") return "KNOWLEDGE";
  if (step.type === "response") return "RESPONSE";
  if (step.type === "thinking") return "DIALOGUE";

  const meta = step.metadata as Record<string, unknown> | null;
  const category = meta?.tool_category
    ? String(meta.tool_category)
    : "";
  const prefix = _SEPARATELY_BILLED[category] || "";
  if (step.type === "tool_call" && prefix) {
    // Return the generic key; the caller will also try a
    // per-tool key when metadata carries a tool_name.
    return prefix + " (tool call)";
  }
  return prefix;
}

/** Build a list of candidate pipeline_key strings to try, in
 *  priority order, so per-tool cost rows (recorded since the
 *  DIALOGUE multi-tool fix) are preferred over the legacy generic
 *  "(tool call)" key. */
function _candidateKeys(
  step: FlowStep,
  prefix: string,
  toolName: string | undefined,
): string[] {
  const keys: string[] = [];
  if (toolName) {
    // Per-tool keys recorded for multi-tool DIALOGUE rounds.
    keys.push(`DIALOGUE (${toolName})`);
    // Also try TOOL_EXECUTION in case the category is billed
    // through the cheap stage (single-tool-per-round).
    keys.push(`${prefix} (${toolName})`);
  }
  // Legacy generic fallback.
  keys.push(`${prefix} (tool call)`);
  return keys;
}

/** Find and consume a cost row by loose substring match across all
 *  per-key queues.  Used for mood/rag steps whose pipeline_key may
 *  vary (e.g. INTRA_SESSION_MOOD). */
function _findSubstringInQueues(
  target: string,
  queues: Record<string, CallChainDetail["steps"]>,
): CallChainDetail["steps"][0] | undefined {
  const t = target.toLowerCase();
  for (const key of Object.keys(queues)) {
    if (key.toLowerCase().includes(t) && queues[key]!.length > 0) {
      return queues[key]!.shift();
    }
  }
  return undefined;
}

export function InlineFlowNodes({ steps, position, costDetail }: Props) {
  const nodes = steps.filter((s) => {
    if (
      s.type === "user_message" ||
      s.type === "response" ||
      s.type === "system_message"
    )
      return false;
    const isPre = PRE_TYPES.has(s.type);
    return position === "pre" ? isPre : !isPre;
  });

  // Build per-key queues from cost rows, sorted by recorded_at so
  // the Nth flow step of a given category gets the Nth cost row.
  const costSteps = costDetail?.steps || [];
  const queues: Record<string, CallChainDetail["steps"]> = {};
  for (const cs of costSteps) {
    const key = cs.pipeline_key;
    if (!queues[key]) queues[key] = [];
    queues[key].push(cs);
  }
  for (const key of Object.keys(queues)) {
    queues[key]!.sort((a, b) => {
      const ta = a.recorded_at || "";
      const tb = b.recorded_at || "";
      return ta.localeCompare(tb);
    });
  }

  // Match each flow node to a cost row, consuming from queues so
  // same-category steps get distinct rows instead of all sharing
  // the same .find() result.
  const stepCosts: (CallChainDetail["steps"][0] | undefined)[] = [];
  if (position === "mid") {
    for (const step of nodes) {
      const target = _resolveTarget(step);
      if (!target) {
        stepCosts.push(undefined);
        continue;
      }
      const meta = (
        step.metadata as Record<string, unknown> | null
      );
      const toolName = meta?.tool_name
        ? String(meta.tool_name)
        : undefined;
      const category = meta?.tool_category
        ? String(meta.tool_category)
        : "";
      const prefix = _SEPARATELY_BILLED[category] || "DIALOGUE";

      let cs: CallChainDetail["steps"][0] | undefined;
      if (step.type === "tool_call") {
        // Try per-tool keys first (DIALOGUE multi-tool rounds),
        // then the legacy generic "(tool call)" fallback.
        const keys = _candidateKeys(step, prefix, toolName);
        for (const key of keys) {
          const queue = queues[key];
          if (queue?.length) {
            cs = queue.shift();
            break;
          }
        }
      } else if (
        step.type === "mood_update" ||
        step.type === "rag_step" ||
        step.type === "response"
      ) {
        // Loose substring match — pipeline_key strings for these
        // vary (e.g. INTRA_SESSION_MOOD).
        cs = _findSubstringInQueues(target, queues);
      } else {
        // thinking and any other types: exact match only.
        // thinking → bare "DIALOGUE" won't match suffixed queue
        // keys, so it stays unpaired (same as before).
        const queue = queues[target];
        cs = queue?.length ? queue.shift() : undefined;
      }
      stepCosts.push(cs);
    }
  }

  // Whatever remains unconsumed in queues are orphans — only in the
  // "mid" position.  "pre" shows System Prompt / Per-Turn Context
  // only (neither is billed separately, so no cost rows match).
  const orphanCostSteps: CallChainDetail["steps"] = [];
  if (position === "mid") {
    for (const q of Object.values(queues)) {
      orphanCostSteps.push(...q);
    }
  }

  const totalNodes = nodes.length + orphanCostSteps.length;
  if (totalNodes === 0) return null;

  return (
    <div
      className={styles.nodesContainer}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{ padding: position === "pre" ? "0 0 6px 36px" : "4px 0 4px 36px" }}
    >
      <div className={styles.nodesRail}>
        {nodes.map((step, i) => (
          <FlowStepNode
            key={`flow-${i}`}
            step={step}
            costStep={stepCosts[i]}
          />
        ))}
        {orphanCostSteps.map((cs, i) => (
          <CostStepNode key={`orphan-${i}`} costStep={cs} />
        ))}
      </div>
    </div>
  );
}

/** Render a cost step that has no matching flow step */
function CostStepNode({ costStep }: { costStep: CallChainDetail["steps"][0] }) {
  const info = pipelineStageInfo(costStep.pipeline_key);
  const label = info.label;
  const color = costStep.pipeline_key.includes("MOOD") ? "#eb459e"
    : costStep.pipeline_key.includes("VALIDATOR") ? "#57f287"
    : costStep.pipeline_key.includes("CLASSIFICATION") ? "#faa61a"
    : costStep.pipeline_key.includes("response)") ? "#5865f2"
    : costStep.pipeline_key.includes("tool call") ? "var(--bs-danger)"
    : "#8b8b8b";

  const handleClick = () => {
    // Build a synthetic flow step from the cost data
    const meta: Record<string, unknown> = {
      model_id: costStep.model_id,
      input_tokens: costStep.input_tokens,
      output_tokens: costStep.output_tokens,
      cost_usd: costStep.cost_usd,
      pipeline_key: costStep.pipeline_key,
    };
    if (costStep.tier_name) meta.tier_name = costStep.tier_name;
    if (costStep.complexity_score != null) meta.complexity_score = costStep.complexity_score;
    if (costStep.skipped) meta.skipped = true;
    if (costStep.prompt_text != null) meta.prompt_text = costStep.prompt_text;
    if (costStep.response_text != null) meta.response_text = costStep.response_text;

    // Build metadata-only content (no prompt/response text per privacy rules)
    let content: string | null = null;
    if (costStep.prompt_char_count != null || costStep.response_char_count != null) {
      const parts: string[] = [];
      if (costStep.prompt_char_count != null) {
        parts.push(`Prompt: ${costStep.prompt_char_count.toLocaleString()} chars`);
      }
      if (costStep.response_char_count != null) {
        parts.push(`Response: ${costStep.response_char_count.toLocaleString()} chars`);
      }
      content = parts.join(" | ");
    }

    const syntheticStep = {
      type: "cost_step",
      label: `${costStep.pipeline_key}`,
      content: content,
      metadata: meta,
    };

    window.dispatchEvent(
      new CustomEvent("airunner:show-flow-detail", {
        detail: { step: syntheticStep },
      }),
    );
  };

  return (
    <div className={styles.costStepNode} onClick={handleClick} title="Click for details">
      {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
      <div className={styles.nodeDotCentered} style={{ background: color }} />
      <div className={styles.nodeContent}>
        {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
        <span className={styles.costStepLabel} style={{ color }}>
          ▶ {label}
        </span>
        {info.description && (
          <span className={styles.costStepDesc}>{info.description}</span>
        )}
        {costStep.response_char_count != null && (
          <span className={styles.costStepChars}>
            {costStep.response_char_count.toLocaleString()} chars
          </span>
        )}
      </div>
      <div className={styles.nodeCostBlock}>
        <span className={styles.nodeModelId}>{costStep.model_id}</span>
        <span className={styles.nodeTokenCount}>
          {costStep.input_tokens.toLocaleString()}→{costStep.output_tokens.toLocaleString()}
        </span>
        {costStep.cost_usd > 0 && (
          <span className={styles.nodeCostValue}>
            ${costStep.cost_usd.toFixed(6)}
          </span>
        )}
      </div>
    </div>
  );
}

function FlowStepNode({ step, costStep }: { step: FlowStep; costStep?: CallChainDetail["steps"][0] }) {
  const style = STEP_STYLE[step.type] || { color: "#8b8b8b", icon: "•" };
  const toolName =
    step.type === "tool_call" && step.metadata
      ? String((step.metadata as Record<string, unknown>).tool_name || "")
      : "";
  const label = step.label.replace(/^(Tool call|Tool result): /, "");
  const maxLen = 60;
  const content =
    step.content && step.content.length > maxLen
      ? step.content.slice(0, maxLen) + "…"
      : step.content || "";
  const hasDetail =
    (step.content?.length ?? 0) > 0 ||
    (step.metadata && Object.keys(step.metadata).length > 0);

  // Pull cost/token data from metadata for right-aligned display
  const meta = step.metadata as Record<string, unknown> | null;
  const costUsd = costStep?.cost_usd ?? (meta?.cost_usd != null ? Number(meta.cost_usd) : null);
  const inputTokens = costStep?.input_tokens ?? (meta?.input_tokens != null ? Number(meta.input_tokens) : null);
  const outputTokens = costStep?.output_tokens ?? (meta?.output_tokens != null ? Number(meta.output_tokens) : null);
  const modelId = costStep?.model_id ?? (meta?.model ? String(meta.model) : null);
  const totalTokens = costStep ? costStep.input_tokens + costStep.output_tokens : null;

  const handleClick = () => {
    if (!hasDetail) return;
    // Dispatch to open in right panel — include costStep so the
    // detail panel can show the same real model/cost as this row.
    window.dispatchEvent(
      new CustomEvent("airunner:show-flow-detail", {
        detail: { step, costStep: costStep ?? undefined },
      }),
    );
  };

  return (
    <div
      className={`${styles.nodeRow} ${hasDetail ? styles.nodeRowClickable : ""}`}
      onClick={handleClick}
      title={hasDetail ? "Click for details" : undefined}
    >
      {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
      <div className={styles.nodeDot} style={{ background: style.color }} />

      <div className={styles.nodeContent}>
        {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
        <span className={styles.nodeLabel} style={{ color: style.color }}>
          {hasDetail && <span className={styles.nodeArrow}>▶</span>}
          {style.icon} {label}
          {toolName && <span className={styles.nodeToolName}>{toolName}</span>}
        </span>
        {content && <span className={styles.nodeTruncated}>{content}</span>}
      </div>

      {(costUsd != null || inputTokens != null || modelId) && (
        <div className={styles.nodeCostBlock}>
          {modelId && <span className={styles.nodeModelId}>{modelId}</span>}
          {inputTokens != null && outputTokens != null && (
            <span className={styles.nodeTokenCount}>
              {inputTokens.toLocaleString()}→{outputTokens.toLocaleString()}
            </span>
          )}
          {costUsd != null && costUsd > 0 && (
            <span className={styles.nodeCostValue}>
              ${costUsd.toFixed(6)}
              {step.type === "thinking" && (
                <span className={styles.nodeCostNote}> (included in response cost)</span>
              )}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
