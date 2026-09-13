/** Admin tool: view any chatbot's agent calendar (superuser only). */

import { useState, useCallback } from "react";
import { request } from "@/api/client-base";
import styles from "./AgentCalendarViewer.module.css";

interface CalendarEvent {
  id: number;
  title: string;
  description: string | null;
  starts_at: string;
  ends_at: string | null;
  all_day: boolean;
  is_recurring_reminder: boolean;
  recurrence_days: string | null;
  deleted: boolean;
}

interface CalendarResponse {
  chatbot_id: number;
  year: number;
  month: number;
  events: CalendarEvent[];
}

interface Props {
  /** The chatbot whose calendar to inspect. */
  chatbotId: number;
}

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export default function AgentCalendarViewer({ chatbotId }: Props) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchCalendar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await request<CalendarResponse>(
        "GET",
        "/api/v1/admin/chatbots/"
        + chatbotId
        + "/calendar?year=" + year
        + "&month=" + month
        + "&include_deleted=" + includeDeleted,
      );
      setEvents(data.events);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load calendar",
      );
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, [chatbotId, year, month, includeDeleted]);

  const prevMonth = () => {
    if (month === 1) {
      setMonth(12);
      setYear(year - 1);
    } else {
      setMonth(month - 1);
    }
  };

  const nextMonth = () => {
    if (month === 12) {
      setMonth(1);
      setYear(year + 1);
    } else {
      setMonth(month + 1);
    }
  };

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <h5 className={styles.headerTitle}>
          Agent Calendar — Chatbot #{chatbotId}
        </h5>
      </div>

      <div className={styles.controls}>
        <button onClick={prevMonth} className={styles.btn}>←</button>
        <span className={styles.monthLabel}>
          {MONTHS[month - 1]} {year}
        </span>
        <button onClick={nextMonth} className={styles.btn}>→</button>
        <button onClick={fetchCalendar} className={styles.btnLoad}>
          Load
        </button>
        <label className={styles.checkLabel}>
          <input
            type="checkbox"
            checked={includeDeleted}
            onChange={(e) => setIncludeDeleted(e.target.checked)}
          />
          {" "}Show deleted
        </label>
      </div>

      {loading && (
        <div className={styles.status}>Loading…</div>
      )}
      {error && (
        <div className={styles.errorText}>{error}</div>
      )}

      {!loading && !error && events.length === 0 && (
        <div className={styles.status}>No events found for this month.</div>
      )}

      {events.map((ev) => {
        const eventClass = [
          styles.eventRow,
          ev.deleted ? styles.deleted : "",
          ev.is_recurring_reminder ? styles.recurring : "",
        ].filter(Boolean).join(" ");

        return (
          <div key={ev.id} className={eventClass}>
            <div className={styles.eventTitle}>
              {ev.deleted && <span className={styles.badgeDeleted}>DELETED</span>}
              {ev.is_recurring_reminder && (
                <span className={styles.badgeRecurring}>RECURRING</span>
              )}
              {ev.title}
            </div>
            <div className={styles.eventMeta}>
              {ev.all_day
                ? ev.starts_at.slice(0, 10) + " (all day)"
                : ev.starts_at.slice(0, 16).replace("T", " ")}
              {ev.ends_at && !ev.all_day && (
                <> — {ev.ends_at.slice(0, 16).replace("T", " ")}</>
              )}
              {ev.recurrence_days && (
                <span className={styles.days}>
                  {" "}[{ev.recurrence_days}]
                </span>
              )}
            </div>
            {ev.description && (
              <div className={styles.eventDesc}>{ev.description}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
