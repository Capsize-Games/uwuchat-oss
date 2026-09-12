/**
 * Shared pipeline step type → color/icon mapping.
 * Used by FlowInspector, InlineFlowNodes, TurnFlowView, and FlowDetailPanel.
 * Single source of truth — edit here, not in three separate files.
 */
export const STEP_STYLE: Record<string, { color: string; icon: string }> = {
  system_prompt: { color: "#8b8b8b", icon: "⚙" },
  per_turn_context: { color: "#8b8b8b", icon: "🔄" },
  semantic_bridge: { color: "var(--theme-premium)", icon: "🔗" },
  user_message: { color: "#5865f2", icon: "👤" },
  rag_step: { color: "#57f287", icon: "📚" },
  thinking: { color: "#faa61a", icon: "💭" },
  tool_call: { color: "var(--bs-danger)", icon: "🔧" },
  tool_result: { color: "#4fbfc9", icon: "📋" },
  mood_update: { color: "#eb459e", icon: "🎭" },
  response: { color: "#5865f2", icon: "🤖" },
  proactive_trigger: { color: "#eb459e", icon: "⚡" },
  system_message: { color: "#8b8b8b", icon: "💬" },
};
