import { useState, useEffect, useCallback, useRef } from "react";
import {
  getSpotifyStatus,
  getSpotifyProfile,
  type SpotifyProfile,
  type SpotifyStatus,
} from "../api/spotify";

interface UseSpotifyProfileResult {
  profile: SpotifyProfile | null;
  status: SpotifyStatus | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

/**
 * Hook to fetch a user's Spotify profile data.
 *
 * Automatically polls the status endpoint every 10 seconds while
 * the scrape is in progress (status is "pending" or "scraping").
 * Once status is "complete", fetches the full profile.
 */
export function useSpotifyProfile(
  userId: number | null,
): UseSpotifyProfileResult {
  const [profile, setProfile] = useState<SpotifyProfile | null>(null);
  const [status, setStatus] = useState<SpotifyStatus | null>(null);
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
      const s = await getSpotifyStatus(userId);
      if (!mountedRef.current) return;
      setStatus(s);
      setError(null);

      if (s.status === "complete") {
        clearPoll();
        const p = await getSpotifyProfile(userId);
        if (!mountedRef.current) return;
        setProfile(p);
        setLoading(false);
      } else if (s.status === "error") {
        clearPoll();
        setError(s.error ?? "Failed to scrape Spotify data");
        setLoading(false);
      } else if (s.status === "pending" || s.status === "scraping") {
        pollTimerRef.current = setTimeout(fetchStatus, 10_000);
      } else {
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