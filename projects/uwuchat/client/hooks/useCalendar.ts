import { useState, useEffect, useCallback, useRef } from "react";
import {
  listCalendarEvents,
  type CalendarEvent,
} from "../api/calendar";

interface UseCalendarResult {
  events: CalendarEvent[];
  loading: boolean;
  error: string | null;
  refresh: (fromDate: string, toDate: string) => void;
}

export function useCalendar(
  chatbotId?: number | null,
): UseCalendarResult {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chatbotIdRef = useRef(chatbotId);
  chatbotIdRef.current = chatbotId;

  const fetch = useCallback(
    async (fromDate: string, toDate: string) => {
      setLoading(true);
      setError(null);
      try {
        const data = await listCalendarEvents(
          fromDate, toDate, chatbotIdRef.current,
        );
        setEvents(data.events);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load calendar",
        );
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    const end = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    fetch(start.toISOString().slice(0, 10), end.toISOString().slice(0, 10));
  }, [fetch, chatbotId]);

  return { events, loading, error, refresh: fetch };
}
