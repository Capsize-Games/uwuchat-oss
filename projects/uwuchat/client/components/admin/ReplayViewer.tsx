import { useState, useEffect } from "react";
import { getEventContext, type ConversationEvent } from "../../api/admin";
import { EVENT_TYPE_COLORS, EVENT_TYPE_LABELS } from "../../utils/eventTypeColors";
import styles from "./ReplayViewer.module.css";

interface Props { eventId: string; onClose: () => void; }

export default function ReplayViewer({ eventId, onClose }: Props) {
  const [events, setEvents] = useState<ConversationEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [path, setPath] = useState<string[]>([]);

  useEffect(() => {
    setLoading(true);
    getEventContext(eventId).then((res) => { setEvents(res.events); setPath(res.event_path ?? []); }).catch(() => {}).finally(() => setLoading(false));
  }, [eventId]);

  return (
    <div className={styles.drawer}>
      <div className={styles.header}>
        <span className={styles.title}>🎬 Event {eventId.slice(0, 8)}</span>
        <button onClick={onClose} className={styles.closeBtn}>×</button>
      </div>
      <div className={styles.scrollBody}>
        {loading && <div className={styles.emptyState}>Loading context…</div>}
        {!loading && events.length === 0 && <div className={styles.emptyState}>No events in context.</div>}
        {events.map((e) => (
          <button key={e.event_id} className={styles.eventBtn} onClick={() => {}}>
            {/* eslint-disable-next-line no-restricted-syntax -- lookup-table color from shared constants */}
            <span className={styles.eventBadge} style={{ background: EVENT_TYPE_COLORS[e.event_type] || "#666" }}>{EVENT_TYPE_LABELS[e.event_type] || e.event_type}</span>
            <span className={styles.eventContent}>{formatSummary(e)}</span>
            <span className={styles.eventActor}>{e.actor}</span>
          </button>
        ))}
        {path.length > 0 && <div className={styles.path}>{path.join(" → ")}</div>}
      </div>
    </div>
  );
}

function formatSummary(e: ConversationEvent): string {
  const p = e.payload as Record<string, unknown> | null; if (!p) return "";
  switch (e.event_type) {
    case "message_append": return String(p.content ?? "").slice(0, 60);
    case "tool_call": return `Tool: ${p.tool_name ?? "?"}`;
    case "tool_result": return `Result: ${p.status ?? "?"}`;
    case "message_delete": return `Removed ${p.messages_removed ?? "?"} msgs`;
    case "conversation_truncate": return `Kept ${p.keep_count ?? "?"} of ${p.original_count ?? "?"}`;
    case "session_start": return `Session #${p.session_id ?? "?"}`;
    case "knowledge_record": return `Fact: ${String(p.fact ?? "").slice(0, 50)}`;
    case "mood_update": return `Mood: ${p.mood ?? "?"}`;
    case "summary_generated": return `${p.summary_type ?? "?"} summary`;
    default: return "";
  }
}
