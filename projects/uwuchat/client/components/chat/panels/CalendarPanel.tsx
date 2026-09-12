import { useCalendar } from "../../../hooks/useCalendar";
import type { CalendarEvent } from "../../../api/calendar";
import styles from "./CalendarPanel.module.css";

function formatDateLabel(dateStr: string): string {
  try { const d = new Date(dateStr + "T12:00:00"); return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }); }
  catch { return dateStr; }
}

function formatTime(isoStr: string): string {
  try { const d = new Date(isoStr); return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }); }
  catch { return isoStr; }
}

function groupEventsByDate(events: CalendarEvent[]): Map<string, CalendarEvent[]> {
  const groups = new Map<string, CalendarEvent[]>();
  for (const event of events) {
    const key = event.starts_at.slice(0, 10);
    const list = groups.get(key); if (list) list.push(event); else groups.set(key, [event]);
  }
  return groups;
}

function EventRow({ event }: { event: CalendarEvent }) {
  return (
    <div className={styles.eventRow}>
      <div className={styles.eventTitle}>{event.title}</div>
      <div className={styles.eventTime}>
        {event.all_day ? "All day" : `${formatTime(event.starts_at)}${event.ends_at ? ` – ${formatTime(event.ends_at)}` : ""}`}
      </div>
      {event.description && <div className={styles.eventDesc}>{event.description}</div>}
    </div>
  );
}

export function CalendarPanel({ chatbotId }: { chatbotId?: number | null }) {
  const { events, loading, error } = useCalendar(chatbotId);
  if (loading) return <div className={styles.stateMsg}>Loading calendar...</div>;
  if (error) return <div className={styles.errorMsg}>{error}</div>;
  if (events.length === 0) return <div className={styles.stateMsg}>No events this month. Ask your UwU to add one — just tell them about your plans!</div>;

  const groups = groupEventsByDate(events);
  return (
    <div className={styles.panel}>
      {[...groups.entries()].map(([dateKey, dayEvents]) => (
        <div key={dateKey}>
          <div className={styles.dateHeader}>{formatDateLabel(dateKey)}</div>
          {dayEvents.map((event) => <EventRow key={event.id} event={event} />)}
        </div>
      ))}
    </div>
  );
}
