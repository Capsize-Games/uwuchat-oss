import { useState, useEffect, useCallback } from "react";
import {
  listJournalEntries,
  type JournalEntry,
} from "../api/journal";

interface UseJournalResult {
  entries: JournalEntry[];
  total: number;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useJournal(): UseJournalResult {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listJournalEntries(30, 0);
      setEntries(data.entries);
      setTotal(data.total);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load journal",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { entries, total, loading, error, refresh: fetch };
}
