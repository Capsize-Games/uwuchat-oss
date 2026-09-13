import { useState, useEffect, useCallback, useRef } from "react";
import {
  getSteamStatus,
  getSteamProfile,
  type SteamProfile,
  type SteamStatus,
} from "../api/steam";

interface UseSteamProfileResult {
  profile: SteamProfile | null;
  status: SteamStatus | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

/**
 * Hook to fetch a user's Steam profile data.
 *
 * Automatically polls the status endpoint every 10 seconds while
 * the scrape is in progress (status is "pending" or "scraping").
 * Once status is "complete", fetches the full profile.
 */
export function useSteamProfile(
  userId: number | null,
): UseSteamProfileResult {
  const [profile, setProfile] = useState<SteamProfile | null>(null);
  const [status, setStatus] = useState<SteamStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const clearPoll = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    if (userId === null) return;
    try {
      const s = await getSteamStatus(userId);
      if (!mountedRef.current) return;
      setStatus(s);
      setError(null);

      if (s.connected) {
        clearPoll();
        const p = await getSteamProfile(userId);
        if (!mountedRef.current) return;
        setProfile(p);
        setLoading(false);
      } else if (s.status === "error") {
        clearPoll();
        setError(s.error ?? "Failed to load Steam data");
        setProfile(null);
        setLoading(false);
      } else {
        // Not connected (e.g. after disconnect) — clear cached data.
        setProfile(null);
        setLoading(false);
      }
    } catch (err) {
      if (!mountedRef.current) return;
      setError(
        err instanceof Error ? err.message : "Failed to fetch status",
      );
      setLoading(false);
    }
  }, [userId, clearPoll]);

  // Listen for steam:disconnected events from other components (e.g.
  // IntegrationsSection in settings) and re-fetch status so the UI
  // reflects the disconnected state.
  useEffect(() => {
    const handler = () => {
      if (userId !== null) {
        setLoading(true);
        setError(null);
        setProfile(null);
        clearPoll();
        fetchStatus();
      }
    };
    window.addEventListener("steam:disconnected", handler);
    return () => window.removeEventListener("steam:disconnected", handler);
  }, [userId, fetchStatus, clearPoll]);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    setProfile(null);
    clearPoll();
    fetchStatus();
  }, [fetchStatus, clearPoll]);

  useEffect(() => {
    mountedRef.current = true;
    if (userId === null) {
      setProfile(null);
      setStatus(null);
      setLoading(false);
      return;
    }
    refresh();
    return () => {
      mountedRef.current = false;
      clearPoll();
    };
  }, [userId, refresh]);

  return { profile, status, loading, error, refresh };
}
