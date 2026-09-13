/**
 * Shared event type → color mapping.
 * Used by EventTimeline, ReplayViewer, InlineEventNodes, and FastSearchStatusPanel.
 * Single source of truth — edit here, not in separate files.
 */
export const EVENT_TYPE_COLORS: Record<string, string> = {
  message_append: "#5865f2",
  tool_call: "#f0a040",
  tool_result: "#f0a040",
  message_delete: "#ed4245",
  conversation_truncate: "#ed4245",
  session_start: "#57f287",
  knowledge_record: "#1abc9c",
  mood_update: "#80848e",
  summary_generated: "#80848e",
  model_used: "#c27bff",
};

export const EVENT_TYPE_LABELS: Record<string, string> = {
  message_append: "📝 Message",
  tool_call: "🔧 Tool Call",
  tool_result: "📋 Result",
  message_delete: "🗑 Deleted",
  conversation_truncate: "✂ Truncated",
  session_start: "▶ Session",
  knowledge_record: "📚 Knowledge",
  mood_update: "🎭 Mood",
  summary_generated: "📄 Summary",
  model_used: "🧠 Model",
};
