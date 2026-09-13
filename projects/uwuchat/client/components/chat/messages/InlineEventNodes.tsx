import type { ConversationEvent } from "../../../api/admin";
import styles from "./InlineEventNodes.module.css";

const TYPE_COLORS: Record<string, string> = {
  message_append: "#5865f2", tool_call: "#f0a040", tool_result: "#f0a040",
  message_delete: "#ed4245", conversation_truncate: "#ed4245", session_start: "#57f287",
  knowledge_record: "#1abc9c", mood_update: "#80848e", summary_generated: "#80848e",
  model_used: "#c27bff",
};

const TYPE_LABELS: Record<string, string> = {
  message_append: "📝 Message", tool_call: "🔧 Tool Call", tool_result: "📋 Result",
  message_delete: "🗑 Deleted", conversation_truncate: "✂ Truncated", session_start: "▶ Session",
  knowledge_record: "📚 Knowledge", mood_update: "🎭 Mood", summary_generated: "📄 Summary",
  model_used: "🧠 Model",
};

interface Props {
  events: ConversationEvent[];
  afterTimestamp?: string;
  beforeTimestamp?: string;
}

export function InlineEventNodes({
  events,
  afterTimestamp,
  beforeTimestamp,
}: Props) {
  const ceiling = beforeTimestamp ?? new Date().toISOString();
  const filtered = events.filter((e) => {
    if (afterTimestamp && e.created_at < afterTimestamp) return false;
    if (e.created_at > ceiling) return false;
    return true;
  });
  if (filtered.length === 0) return null;

  return (
    <div className={styles.wrap}>
      <div className={styles.timeline}>
        <div className={styles.header}>Events · {filtered.length}</div>
        {filtered.map((ev) => {
          const color = TYPE_COLORS[ev.event_type] || "#8b8b8b";
          const label = TYPE_LABELS[ev.event_type] || ev.event_type;
          const time = new Date(ev.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
          const payloadPreview = ev.payload
            ? (ev.payload.content ? String(ev.payload.content).slice(0, 50)
              : ev.payload.tool_name ? `tool: ${ev.payload.tool_name}`
              : ev.payload.model_id ? `${ev.payload.model_id} (${ev.payload.pipeline_key || ""})`
              : JSON.stringify(ev.payload).slice(0, 50)) : "";

          return (
            <div key={ev.event_id} className={styles.eventRow}>
              {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
              <div className={styles.dot} style={{ background: color }} />
              {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
              <span className={styles.eventLabel} style={{ color }}>{label}</span>
              <span className={styles.eventTime}>{time}</span>
              {payloadPreview && <span className={styles.eventPreview}>{payloadPreview}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
