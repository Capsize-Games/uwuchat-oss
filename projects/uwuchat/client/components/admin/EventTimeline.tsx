import { useState, useEffect, useCallback } from "react";
import { listAdminEvents, type ConversationEvent } from "../../api/admin";
import { EVENT_TYPE_COLORS } from "../../utils/eventTypeColors";
import ReplayViewer from "./ReplayViewer";
import styles from "./EventTimeline.module.css";

interface Props { chatbotId: number; onClose: () => void; }

const ALL_TYPES = Object.keys(EVENT_TYPE_COLORS);

export default function EventTimeline({ chatbotId, onClose }: Props) {
  const [events, setEvents] = useState<ConversationEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [replayEventId, setReplayEventId] = useState<string | null>(null);
  const [filter, setFilter] = useState<Set<string>>(new Set(ALL_TYPES));
  const [loading, setLoading] = useState(false);

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    try { const types = filter.size < ALL_TYPES.length ? Array.from(filter).join(",") : undefined; const res = await listAdminEvents(chatbotId, { event_types: types, limit: 100 }); setEvents(res.events); setTotal(res.total); } catch {} finally { setLoading(false); }
  }, [chatbotId, filter]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  return (
    <div className={styles.drawer}>
      <div className={styles.header}>
        <span className={styles.title}>📋 Event Log ({total})</span>
        <button onClick={onClose} className={styles.closeBtn}>×</button>
      </div>
      <div className={styles.filterBar}>
        {ALL_TYPES.map((t) => (
          // eslint-disable-next-line no-restricted-syntax -- lookup-table color from shared constants
          <label key={t} className={styles.filterLabel} style={{ color: filter.has(t) ? EVENT_TYPE_COLORS[t] : "var(--theme-text-muted)", opacity: filter.has(t) ? 1 : 0.4 }}>
            <input type="checkbox" checked={filter.has(t)} onChange={() => setFilter((prev) => { const n = new Set(prev); n.has(t) ? n.delete(t) : n.add(t); return n; })} className={styles.filterCheckbox} />
            {t.replace(/_/g, " ")}
          </label>
        ))}
      </div>
      <div className={styles.eventList}>
        {loading && events.length === 0 && <div className={styles.emptyState}>Loading…</div>}
        {!loading && events.length === 0 && <div className={styles.emptyState}>No events found.</div>}
        {events.map((e) => (
          <button key={e.event_id} onClick={() => setReplayEventId(e.event_id)} className={styles.eventBtn}>
            {/* eslint-disable-next-line no-restricted-syntax -- lookup-table color from shared constants */}
            <span className={styles.eventBadge} style={{ background: EVENT_TYPE_COLORS[e.event_type] || "#666" }}>{e.event_type}</span>
            <span className={styles.eventSummary}>{formatSummary(e)}</span>
            <span className={styles.eventActor}>{e.actor}</span>
          </button>
        ))}
      </div>
      {replayEventId && <ReplayViewer eventId={replayEventId} onClose={() => setReplayEventId(null)} />}
    </div>
  );
}

function formatSummary(e: ConversationEvent): string {
  const p = e.payload as Record<string, unknown> | null; if (!p) return "";
  switch (e.event_type) {
    case "message_append": return String(p.content ?? "").slice(0, 60);
    case "tool_call": return `Tool: ${p.tool_name ?? "?"}`;
    case "tool_result": return `Result: ${p.status ?? "?"}`;
    case "message_delete": return `Removed ${p.messages_removed ?? "?"} msgs @ idx ${p.visible_index ?? "?"}`;
    case "conversation_truncate": return `Kept ${p.keep_count ?? "?"} of ${p.original_count ?? "?"}`;
    case "session_start": return `Session #${p.session_id ?? "?"}`;
    case "knowledge_record": return `Fact: ${String(p.fact ?? "").slice(0, 50)}`;
    case "mood_update": return `Mood: ${p.mood ?? "?"}`;
    case "summary_generated": return `${p.summary_type ?? "?"} summary (${p.char_count ?? "?"} chars)`;
    default: return "";
  }
}
