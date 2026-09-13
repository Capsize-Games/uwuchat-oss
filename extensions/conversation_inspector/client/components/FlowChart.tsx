/**
 * Custom SVG-based flow chart showing the AI agent conversation flow.
 *
 * Renders color-coded nodes connected by arrows in a vertical layout.
 * Click a node to open the detail panel showing full content.
 * Designed to work without external dependencies (no reactflow needed).
 */

import { useCallback, useState } from "react";
import type { FlowStep, TurnData } from "../api";
import DetailPanel from "./DetailPanel";

interface FlowChartProps {
  turns: TurnData[];
  systemPromptParts: Record<string, string> | null;
}

/** Color map for node types. */
const NODE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  system_prompt:      { bg: "#EEF2FF", text: "#3730A3", border: "#A5B4FC" },
  per_turn_context:   { bg: "#ECFDF5", text: "#065F46", border: "#34D399" },
  user_message:       { bg: "#DBEAFE", text: "#1E40AF", border: "#93C5FD" },
  rag_step:           { bg: "#D1FAE5", text: "#065F46", border: "#6EE7B7" },
  thinking:           { bg: "#FEF3C7", text: "#92400E", border: "#FCD34D" },
  tool_call:          { bg: "#FEE2E2", text: "#991B1B", border: "#FCA5A5" },
  tool_result:        { bg: "#CCFBF1", text: "#115E59", border: "#5EEAD4" },
  mood_update:        { bg: "#FDF4FF", text: "#7E22CE", border: "#D8B4FE" },
  response:           { bg: "#E0E7FF", text: "#3730A3", border: "#A5B4FC" },
  system_message:     { bg: "#F3F4F6", text: "#374151", border: "#D1D5DB" },
  proactive_trigger:  { bg: "#FFF7ED", text: "#92400E", border: "#FCD34D" },
};

/** Emoji/icons for node types. */
const NODE_ICONS: Record<string, string> = {
  system_prompt:     "⚙️",
  per_turn_context:  "💉",
  user_message:      "👤",
  rag_step:          "📎",
  thinking:          "💭",
  tool_call:         "🔧",
  tool_result:       "📋",
  mood_update:       "🎭",
  response:          "💬",
  system_message:    "🔔",
  proactive_trigger: "🤖",
};

/** Layout constants. */
const LEFT_COLUMN_WIDTH = 140;
const NODE_WIDTH = 320;
const NODE_HEIGHT = 58;
const NODE_GAP = 14;
const TURN_GAP = 44;
const TURN_LABEL_HEIGHT = 44;
const PADDING_X = LEFT_COLUMN_WIDTH + 16;
const PADDING_Y = 20;
const ARROW_SIZE = 8;

/** Truncate content for display in node. */
function truncate(text: string, maxLen: number): string {
  if (!text) return "";
  const cleaned = text.replace(/\n/g, " ").trim();
  if (cleaned.length <= maxLen) return cleaned;
  return cleaned.slice(0, maxLen - 3) + "...";
}

function formatTimestamp(ts: string): string {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts.slice(0, 19).replace("T", " ");
    const pad = (n: number) => String(n).padStart(2, "0");
    return (
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
      `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
    );
  } catch {
    return ts.slice(0, 19);
  }
}

export default function FlowChart({ turns, systemPromptParts }: FlowChartProps) {
  const [selectedStep, setSelectedStep] = useState<FlowStep | null>(null);
  const [hoveredNode, setHoveredNode] = useState<number | null>(null);

  const handleNodeClick = useCallback((step: FlowStep) => {
    setSelectedStep(step);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setSelectedStep(null);
  }, []);

  if (turns.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "#9aa0ab" }}>
        No flow data available. Select a conversation to inspect.
      </div>
    );
  }

  interface LayoutNode {
    step: FlowStep;
    turnIndex: number;
    stepIndex: number;
    globalIndex: number;
    x: number;
    y: number;
  }

  const nodes: LayoutNode[] = [];
  let globalIndex = 0;
  let yOffset = PADDING_Y;

  // Pre-compute each turn label's y position
  const turnLabelYs: number[] = [];
  for (let ti = 0; ti < turns.length; ti++) {
    turnLabelYs.push(yOffset);
    yOffset += TURN_LABEL_HEIGHT;
    for (let si = 0; si < turns[ti].flow_steps.length; si++) {
      nodes.push({
        step: turns[ti].flow_steps[si],
        turnIndex: ti,
        stepIndex: si,
        globalIndex,
        x: PADDING_X,
        y: yOffset,
      });
      globalIndex++;
      yOffset += NODE_HEIGHT + NODE_GAP;
    }
    yOffset += TURN_GAP - NODE_GAP;
  }

  // Calculate per-turn metadata for the label (mood, model, timestamp)
  function getTurnSummary(turn: TurnData): { mood?: string; model?: string; timestamp?: string } {
    const mood = turn.flow_steps.find((s) => s.type === "mood_update");
    const model = turn.model as string | undefined;
    const ts = turn.user_message?.timestamp as string | undefined;
    return {
      mood: mood ? String((mood.metadata?.arguments as Record<string, string>)?.mood ?? "") : undefined,
      model,
      timestamp: ts,
    };
  }

  const totalHeight = yOffset + PADDING_Y;
  const svgWidth = PADDING_X + NODE_WIDTH + PADDING_X + 220;
  const conversationTotalChars = turns.reduce(
    (sum, t) => sum + (t.total_characters || 0), 0,
  );
  const conversationTotalTokens = turns.reduce(
    (sum, t) => sum + (t.total_tokens || 0), 0,
  );

  return (
    <div className="cip-flow-wrapper">
      <svg
        width={svgWidth}
        height={Math.max(totalHeight, 400)}
        className="cip-flow-svg"
        viewBox={`0 0 ${svgWidth} ${Math.max(totalHeight, 400)}`}
      >
        {/* Arrow markers */}
        <defs>
          <marker
            id="arrowhead"
            markerWidth={ARROW_SIZE}
            markerHeight={ARROW_SIZE}
            refX={ARROW_SIZE / 2}
            refY={ARROW_SIZE / 2}
            orient="auto"
          >
            <polygon
              points={`0,0 ${ARROW_SIZE},${ARROW_SIZE / 2} 0,${ARROW_SIZE}`}
              fill="#9CA3AF"
            />
          </marker>
        </defs>

        {/* Left column: conversation totals */}
        <rect
          x={0}
          y={0}
          width={LEFT_COLUMN_WIDTH}
          height={Math.max(totalHeight, 400)}
          fill="#1c1f26"
          rx={0}
        />
        {/* Column header */}
        <text
          x={LEFT_COLUMN_WIDTH / 2}
          y={14}
          textAnchor="middle"
          dominantBaseline="middle"
          fill="#9aa0ab"
          fontSize={8}
          fontWeight={700}
          letterSpacing="0.5px"
        >
          CONVERSATION TOTALS
        </text>
        <text
          x={10}
          y={14 + 22}
          textAnchor="start"
          dominantBaseline="middle"
          fill="#9aa0ab"
          fontSize={10}
          fontWeight={600}
        >
          Chars:
        </text>
        <text
          x={LEFT_COLUMN_WIDTH - 10}
          y={14 + 22}
          textAnchor="end"
          dominantBaseline="middle"
          fill="#e6e8eb"
          fontSize={10}
          fontWeight={700}
        >
          {conversationTotalChars.toLocaleString()}
        </text>
        <text
          x={10}
          y={14 + 40}
          textAnchor="start"
          dominantBaseline="middle"
          fill="#9aa0ab"
          fontSize={10}
          fontWeight={600}
        >
          Tokens:
        </text>
        <text
          x={LEFT_COLUMN_WIDTH - 10}
          y={14 + 40}
          textAnchor="end"
          dominantBaseline="middle"
          fill="#e6e8eb"
          fontSize={10}
          fontWeight={700}
        >
          {conversationTotalTokens.toLocaleString()}
        </text>
        {/* Divider below totals */}
        <line
          x1={8}
          y1={14 + 56}
          x2={LEFT_COLUMN_WIDTH - 8}
          y2={14 + 56}
          stroke="#2a2e37"
          strokeWidth={1}
        />
        {/* Turn labels */}
        {turns.map((turn, ti) => {
          const labelY = turnLabelYs[ti];
          const rag = turn.rag_context as Record<string, unknown> | null;
          const isRagActive = rag?.is_rag_active === true;
          const summary = getTurnSummary(turn);

          const userContent = turn.user_message
            ? truncate(String(turn.user_message!.content || ""), 35)
            : "";

          const isProactive = !!(turn as Record<string, unknown>).is_proactive;
          let labelText = `Turn ${ti + 1}`;
          if (isProactive) {
            labelText += " 🤖 proactive";
          } else {
            if (isRagActive) labelText += " 📎";
            if (summary.mood) labelText += ` 🎭${summary.mood}`;
            if (userContent) labelText += ` — "${userContent}"`;
          }

          const tsLabel = summary.timestamp
            ? formatTimestamp(String(summary.timestamp))
            : "";

          const tChars = (turn.total_characters || 0).toLocaleString();
          const tTokens = (turn.total_tokens || 0).toLocaleString();
          const statsLabel = `${tChars} characters · ${tTokens} tokens`;

          return (
            <g key={`turn-label-${ti}`}>
              <rect
                x={PADDING_X}
                y={labelY}
                width={NODE_WIDTH}
                height={TURN_LABEL_HEIGHT}
                rx={4}
                fill={isRagActive ? "#0d2b1e" : "#1c1f26"}
                stroke={isRagActive ? "#166534" : "#2a2e37"}
                strokeWidth={isRagActive ? 1.5 : 1}
              />
              {/* Line 1: Turn N — "<preview>" */}
              <text
                x={PADDING_X + 10}
                y={labelY + 14}
                textAnchor="start"
                dominantBaseline="middle"
                fill="#e6e8eb"
                fontSize={11}
                fontWeight={600}
              >
                {labelText}
              </text>
              {/* Line 2: stats (left) + timestamp (right) */}
              <text
                x={PADDING_X + 10}
                y={labelY + 30}
                textAnchor="start"
                dominantBaseline="middle"
                fill="#9aa0ab"
                fontSize={10}
              >
                {statsLabel}
              </text>
              {tsLabel && (
                <text
                  x={PADDING_X + NODE_WIDTH - 6}
                  y={labelY + 30}
                  textAnchor="end"
                  dominantBaseline="middle"
                  fill="#9aa0ab"
                  fontSize={10}
                >
                  {tsLabel}
                </text>
              )}
            </g>
          );
        })}

        {/* Edges (arrows between nodes) */}
        {nodes.map((node, i) => {
          if (i === nodes.length - 1) return null;
          const nextNode = nodes[i + 1];
          const x1 = PADDING_X + NODE_WIDTH / 2;
          const y1 = node.y + NODE_HEIGHT;
          const x2 = PADDING_X + NODE_WIDTH / 2;
          const y2 = nextNode.y;
          const isTurnBoundary = node.turnIndex !== nextNode.turnIndex;

          return (
            <line
              key={`edge-${i}`}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2 - (isTurnBoundary ? 4 : 0)}
              stroke="#3a3f4a"
              strokeWidth={isTurnBoundary ? 1.5 : 1}
              strokeDasharray={isTurnBoundary ? "4 3" : undefined}
              markerEnd={isTurnBoundary ? undefined : "url(#arrowhead)"}
            />
          );
        })}

        {/* Nodes */}
        {nodes.map((node, i) => {
          const colors = NODE_COLORS[node.step.type] || {
            bg: "#1e2128",
            text: "#9aa0ab",
            border: "#2a2e37",
          };
          const icon = NODE_ICONS[node.step.type] || "•";
          const isHovered = hoveredNode === i;
          const isSelected =
            selectedStep === node.step ||
            (selectedStep?.type === node.step.type &&
              selectedStep?.content === node.step.content &&
              selectedStep?.label === node.step.label);

          // Secondary line: timestamp + token info
          const meta = node.step.metadata || {};
          const ts = meta.timestamp ? formatTimestamp(String(meta.timestamp)) : "";
          const tokens = meta.token_estimate ? `~${meta.token_estimate} tok` : "";
          const model = meta.model ? truncate(String(meta.model).split("/").pop() || "", 22) : "";
          const secondLine = [ts, tokens, model].filter(Boolean).join("  ·  ");

          return (
            <g
              key={`node-${i}`}
              onClick={() => handleNodeClick(node.step)}
              onMouseEnter={() => setHoveredNode(i)}
              onMouseLeave={() => setHoveredNode(null)}
              style={{ cursor: "pointer" }}
            >
              <rect
                x={node.x}
                y={node.y}
                width={NODE_WIDTH}
                height={NODE_HEIGHT}
                rx={8}
                fill={colors.bg}
                stroke={
                  isSelected
                    ? colors.text
                    : isHovered
                    ? colors.border
                    : "#2a2e37"
                }
                strokeWidth={isSelected ? 2 : 1}
                filter={
                  isHovered
                    ? "drop-shadow(0 2px 8px rgba(0,0,0,0.5))"
                    : undefined
                }
              />
              {/* Icon */}
              <text
                x={node.x + 12}
                y={node.y + NODE_HEIGHT / 2}
                fontSize={15}
                dominantBaseline="middle"
              >
                {icon}
              </text>
              {/* Label */}
              <text
                x={node.x + 34}
                y={node.y + 18}
                fill={colors.text}
                fontSize={12}
                fontWeight={600}
                dominantBaseline="middle"
              >
                {truncate(node.step.label, 38)}
              </text>
              {/* Content preview */}
              <text
                x={node.x + 34}
                y={node.y + 33}
                fill={colors.text}
                fontSize={10}
                opacity={0.65}
                dominantBaseline="middle"
              >
                {truncate(node.step.content || "", 40)}
              </text>
              {/* Metadata line: timestamp / tokens / model */}
              {secondLine && (
                <text
                  x={node.x + 34}
                  y={node.y + NODE_HEIGHT - 8}
                  fill={colors.text}
                  fontSize={9}
                  opacity={0.5}
                  dominantBaseline="middle"
                >
                  {secondLine}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Detail panel overlay */}
      {selectedStep && (
        <DetailPanel
          step={selectedStep}
          systemPromptParts={systemPromptParts}
          onClose={handleCloseDetail}
        />
      )}
    </div>
  );
}
