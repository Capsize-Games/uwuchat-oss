/**
 * Mermaid diagram generator for conversation inspection data.
 *
 * Converts flow data (turns + flow steps) and cost data (call chains) into a
 * Mermaid flowchart that can be pasted into any .md file for visualization.
 */
import type {
  ConversationFlowResponse,
  FlowStep,
  TurnData,
} from "../../../../extensions/conversation_inspector/client/api";
import type { CallChainDetail, CallChainStep } from "../../types/pipeline";

interface MessageLike {
  role?: string;
  content?: string;
  call_chain_id?: string | null;
}

/* ── Step display helpers ───────────────────────────────────────── */

const STEP_STYLE: Record<string, { icon: string; label: string }> = {
  system_prompt: { icon: "⚙", label: "System Prompt" },
  per_turn_context: { icon: "🔄", label: "Per-Turn Context" },
  semantic_bridge: { icon: "🔗", label: "Semantic Bridge" },
  user_message: { icon: "👤", label: "User" },
  rag_step: { icon: "📚", label: "RAG" },
  thinking: { icon: "💭", label: "Thinking" },
  tool_call: { icon: "🔧", label: "Tool Call" },
  tool_result: { icon: "📋", label: "Tool Result" },
  mood_update: { icon: "🎭", label: "Mood Update" },
  response: { icon: "🤖", label: "Response" },
  proactive_trigger: { icon: "⚡", label: "Proactive" },
  system_message: { icon: "💬", label: "System" },
};

const PRE_TYPES = new Set(["system_prompt", "per_turn_context", "semantic_bridge"]);

/** Escape any double-quote characters in Mermaid node text. */
function esc(s: string): string {
  return s.replace(/"/g, "#quot;").replace(/\n/g, "<br/>");
}

/** Truncate a string to maxLen, appending "…" if truncated. */
function trunc(s: string, maxLen = 60): string {
  if (s.length <= maxLen) return s;
  return s.slice(0, maxLen) + "…";
}

/** Format a cost step's label for Mermaid display. */
function costLabel(cs: CallChainStep): string {
  const key = cs.pipeline_key
    .replace(/^DIALOGUE /, "")
    .replace(/^INTRA_SESSION_/, "")
    .replace(/_/g, " ");
  return key.replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Build a rich node label for a cost step (orphan cost data). */
function orphanCostNodeLabel(cs: CallChainStep): string {
  const parts: string[] = [`▶ ${costLabel(cs)}`];
  if (cs.model_id) parts.push(`model: ${cs.model_id}`);
  parts.push(`${cs.input_tokens.toLocaleString()}→${cs.output_tokens.toLocaleString()} tok`);
  if (cs.cost_usd > 0) parts.push(`$${cs.cost_usd.toFixed(6)}`);
  return esc(parts.join("<br/>"));
}

/** Build a rich node label for a flow step with optional cost data. */
function stepNodeLabel(
  step: FlowStep,
  costStep?: CallChainStep,
): string {
  const s = STEP_STYLE[step.type] || { icon: "•", label: step.type };
  const toolName =
    step.type === "tool_call" && step.metadata
      ? String((step.metadata as Record<string, unknown>).tool_name || "")
      : "";
  const label = toolName
    ? `${s.icon} ${s.label}: ${toolName}`
    : `${s.icon} ${s.label}`;

  const lines: string[] = [label];

  if (costStep) {
    if (costStep.model_id) lines.push(`model: ${costStep.model_id}`);
    lines.push(
      `${costStep.input_tokens.toLocaleString()}→${costStep.output_tokens.toLocaleString()} tok`,
    );
    if (costStep.cost_usd > 0) lines.push(`$${costStep.cost_usd.toFixed(6)}`);
  }

  // Show content preview for certain step types
  if (step.content) {
    const preview = trunc(step.content, 50);
    lines.push(`<i>${esc(preview)}</i>`);
  }

  return esc(lines.join("<br/>"));
}

/* ── Cost matching helpers ─────────────────────────────────────── */

/** Match a flow step type to a CallChainStep by pipeline_key. */
function findCostStep(
  flowType: string,
  costSteps: CallChainStep[],
): CallChainStep | undefined {
  const map: Record<string, string> = {
    mood_update: "MOOD",
    tool_call: "tool call",
    rag_step: "KNOWLEDGE",
  };
  const target = map[flowType] || "";
  if (!target) return undefined;
  return costSteps.find((cs) =>
    cs.pipeline_key.toLowerCase().includes(target.toLowerCase()),
  );
}

/** Find the cost detail for a turn by matching messages to flow data. */
function findTurnCost(
  turn: TurnData,
  messages: MessageLike[],
  costMap: Record<string, CallChainDetail>,
): CallChainDetail | null {
  const um = turn.user_message;
  if (!um || typeof um !== "object") return null;
  const turnContent = String(
    (um as Record<string, unknown>).content || "",
  ).slice(0, 80).trim();
  if (!turnContent) return null;

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    if (
      msg.role !== "user" ||
      !msg.content ||
      msg.content.slice(0, 80).trim() !== turnContent
    ) {
      continue;
    }
    // Found the user message — look for next assistant message with call_chain_id
    for (let j = i + 1; j < messages.length; j++) {
      if (
        messages[j]?.role === "assistant" &&
        messages[j]?.call_chain_id
      ) {
        return costMap[messages[j].call_chain_id!] || null;
      }
    }
    break;
  }
  return null;
}

/* ── Mermaid generator ─────────────────────────────────────────── */

export interface MermaidOptions {
  /** Max content preview length per step (default 50). */
  maxContentLen?: number;
}

/**
 * Generate a Mermaid flowchart string from inspection data.
 *
 * Produces a `flowchart TD` diagram with one subgraph per turn.
 * Each subgraph contains nodes for the flow steps rendered in order:
 *   pre-nodes (system_prompt, per_turn_context) → user message →
 *   mid-nodes (tool_call, tool_result, thinking, etc.) → response
 * Orphan cost steps (cost data with no matching flow step) are included.
 */
export function generateInspectionMermaid(
  flowData: ConversationFlowResponse,
  costMap: Record<string, CallChainDetail>,
  messages: MessageLike[],
  _opts?: MermaidOptions,
): string {
  const lines: string[] = ["```mermaid", "flowchart TD"];

  if (flowData.turns.length === 0) {
    lines.push("  EMPTY[No turns recorded]");
    lines.push("```");
    return lines.join("\n");
  }

  const prevTurnIds: string[] = [];

  for (let ti = 0; ti < flowData.turns.length; ti++) {
    const turn = flowData.turns[ti];
    const costDetail = findTurnCost(turn, messages, costMap);
    const costSteps = costDetail?.steps || [];
    const turnId = `T${ti}`;

    // User message preview for subgraph title
    const userPreview = (() => {
      const um = turn.user_message;
      if (um && typeof um === "object") {
        return trunc(
          String((um as Record<string, unknown>).content || ""),
          40,
        );
      }
      return "";
    })();

    // Build subgraph header with title line
    const title = esc(userPreview ? `Turn ${ti + 1}: "${userPreview}"` : `Turn ${ti + 1}`);
    const tokInfo =
      turn.total_tokens > 0 ? ` | ${turn.total_tokens.toLocaleString()} tok` : "";
    const costInfo =
      costDetail && costDetail.total_cost_usd > 0
        ? ` | $${costDetail.total_cost_usd.toFixed(6)}`
        : "";
    lines.push(`  subgraph ${turnId}["${title}${tokInfo}${costInfo}"]`);
    lines.push("    direction LR");

    const nodeIds: string[] = [];
    let stepIdx = 0;

    // Pre-nodes: system_prompt, per_turn_context
    for (const step of turn.flow_steps) {
      if (!PRE_TYPES.has(step.type)) continue;
      const nid = makeNodeId(ti, stepIdx++);
      const cs = findCostStep(step.type, costSteps);
      lines.push(`    ${nid}["${stepNodeLabel(step, cs)}"]`);
      nodeIds.push(nid);
    }

    // User message node
    {
      const nid = makeNodeId(ti, stepIdx++);
      const contentPreview = userPreview ? `: "${userPreview}"` : "";
      const label = esc(`👤 User${contentPreview}`);
      lines.push(`    ${nid}["${label}"]`);
      nodeIds.push(nid);
    }

    // Mid-nodes: tool calls, tool results, thinking, rag, mood, etc.
    const matchedPipelineKeys = new Set<string>();
    for (const step of turn.flow_steps) {
      if (
        PRE_TYPES.has(step.type) ||
        step.type === "user_message" ||
        step.type === "response" ||
        step.type === "system_message"
      ) {
        continue;
      }
      const nid = makeNodeId(ti, stepIdx++);
      const cs = findCostStep(step.type, costSteps);
      if (cs) matchedPipelineKeys.add(cs.pipeline_key);
      lines.push(`    ${nid}["${stepNodeLabel(step, cs)}"]`);
      nodeIds.push(nid);
    }

    // Orphan cost steps (cost data with no matching flow step)
    for (const cs of costSteps) {
      if (matchedPipelineKeys.has(cs.pipeline_key)) continue;
      if (cs.skipped) continue;
      const nid = makeNodeId(ti, stepIdx++);
      lines.push(`    ${nid}["${orphanCostNodeLabel(cs)}"]`);
      nodeIds.push(nid);
    }

    // Response node
    {
      const responseStep = turn.flow_steps.find(
        (s: FlowStep) => s.type === "response",
      );
      const nid = makeNodeId(ti, stepIdx++);
      const respCs = costSteps.find(
        (cs) =>
          cs.pipeline_key.toLowerCase().includes("response)") ||
          cs.pipeline_key.toLowerCase().includes("dialogue"),
      );
      // Use response step data if available, otherwise just label
      const label = responseStep
        ? stepNodeLabel(responseStep, respCs)
        : esc("🤖 Response");
      lines.push(`    ${nid}["${label}"]`);
      nodeIds.push(nid);
    }

    // System message node
    {
      const sysStep = turn.flow_steps.find(
        (s: FlowStep) => s.type === "system_message",
      );
      if (sysStep) {
        const nid = makeNodeId(ti, stepIdx++);
        lines.push(`    ${nid}["${stepNodeLabel(sysStep)}"]`);
        nodeIds.push(nid);
      }
    }

    if (nodeIds.length === 0) {
      lines.push(`    ${makeNodeId(ti, 0)}["(empty turn)"]`);
    }

    // Connect nodes in sequence
    for (let i = 1; i < nodeIds.length; i++) {
      lines.push(`    ${nodeIds[i - 1]} --> ${nodeIds[i]}`);
    }

    lines.push("  end");

    // Connect subgraphs sequentially
    if (prevTurnIds.length > 0) {
      lines.push(`  ${prevTurnIds[prevTurnIds.length - 1]} --> ${turnId}`);
    }
    prevTurnIds.push(turnId);
  }

  lines.push("```");
  return lines.join("\n");
}

/**
 * Generate a Mermaid diagram for a single turn.
 *
 * Takes a single TurnData, optional cost detail, and a display index
 * (shown as "Turn N" in the diagram title). Produces a standalone
 * flowchart that can be pasted into any .md file.
 */
export function generateTurnMermaid(
  turn: TurnData,
  costDetail: CallChainDetail | null,
  turnNumber: number,
): string {
  const lines: string[] = ["```mermaid", "flowchart TD"];
  const costSteps = costDetail?.steps || [];

  const userPreview = (() => {
    const um = turn.user_message;
    if (um && typeof um === "object") {
      return trunc(
        String((um as Record<string, unknown>).content || ""),
        40,
      );
    }
    return "";
  })();

  const title = esc(
    userPreview
      ? `Turn ${turnNumber}: "${userPreview}"`
      : `Turn ${turnNumber}`,
  );
  const tokInfo =
    turn.total_tokens > 0
      ? ` | ${turn.total_tokens.toLocaleString()} tok`
      : "";
  const costInfo =
    costDetail && costDetail.total_cost_usd > 0
      ? ` | $${costDetail.total_cost_usd.toFixed(6)}`
      : "";

  lines.push(
    `  subgraph T0["${title}${tokInfo}${costInfo}"]`,
  );
  lines.push("    direction LR");

  const nodeIds: string[] = [];
  let stepIdx = 0;
  const tid = "T0";

  // Pre-nodes
  for (const step of turn.flow_steps) {
    if (!PRE_TYPES.has(step.type)) continue;
    const nid = makeNodeId(0, stepIdx++);
    const cs = findCostStep(step.type, costSteps);
    lines.push(`    ${nid}["${stepNodeLabel(step, cs)}"]`);
    nodeIds.push(nid);
  }

  // User message
  {
    const nid = makeNodeId(0, stepIdx++);
    const preview = userPreview ? `: "${userPreview}"` : "";
    lines.push(`    ${nid}["${esc(`👤 User${preview}`)}"]`);
    nodeIds.push(nid);
  }

  // Mid-nodes
  const matchedKeys = new Set<string>();
  for (const step of turn.flow_steps) {
    if (
      PRE_TYPES.has(step.type) ||
      step.type === "user_message" ||
      step.type === "response" ||
      step.type === "system_message"
    ) {
      continue;
    }
    const nid = makeNodeId(0, stepIdx++);
    const cs = findCostStep(step.type, costSteps);
    if (cs) matchedKeys.add(cs.pipeline_key);
    lines.push(`    ${nid}["${stepNodeLabel(step, cs)}"]`);
    nodeIds.push(nid);
  }

  // Orphan cost steps
  for (const cs of costSteps) {
    if (matchedKeys.has(cs.pipeline_key)) continue;
    if (cs.skipped) continue;
    const nid = makeNodeId(0, stepIdx++);
    lines.push(`    ${nid}["${orphanCostNodeLabel(cs)}"]`);
    nodeIds.push(nid);
  }

  // Response
  {
    const responseStep = turn.flow_steps.find(
      (s: FlowStep) => s.type === "response",
    );
    const nid = makeNodeId(0, stepIdx++);
    const respCs = costSteps.find(
      (cs: CallChainStep) =>
        cs.pipeline_key.toLowerCase().includes("response)") ||
        cs.pipeline_key.toLowerCase().includes("dialogue"),
    );
    const label = responseStep
      ? stepNodeLabel(responseStep, respCs)
      : esc("🤖 Response");
    lines.push(`    ${nid}["${label}"]`);
    nodeIds.push(nid);
  }

  // System message
  {
    const sysStep = turn.flow_steps.find(
      (s: FlowStep) => s.type === "system_message",
    );
    if (sysStep) {
      const nid = makeNodeId(0, stepIdx++);
      lines.push(`    ${nid}["${stepNodeLabel(sysStep)}"]`);
      nodeIds.push(nid);
    }
  }

  if (nodeIds.length === 0) {
    lines.push(`    ${makeNodeId(0, 0)}["(empty turn)"]`);
  }

  for (let i = 1; i < nodeIds.length; i++) {
    lines.push(`    ${nodeIds[i - 1]} --> ${nodeIds[i]}`);
  }

  lines.push("  end");
  lines.push("```");
  return lines.join("\n");
}

/** Generate a stable, Mermaid-safe node ID. */
function makeNodeId(turnIdx: number, stepIdx: number): string {
  return `T${turnIdx}S${stepIdx}`;
}
