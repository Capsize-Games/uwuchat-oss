import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./useAuth";
import {
  getItchStatus,
  getItchProfile,
  type ItchioStatus,
} from "../api/itchio";
import type { ItchioGame } from "../api/itchio";

interface UseItchioProfileResult {
  connected: boolean;
  loading: boolean;
  games: ItchioGame[];
  displayName: string | null;
  coverUrl: string | null;
  error: string | null;
}

export function useItchioProfile(
  userId: number | null,
): UseItchioProfileResult {
  const { accessToken } = useAuth();
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [games, setGames] = useState<ItchioGame[]>([]);
  const [displayName, setDisplayName] = useState<string | null>(null);
  const [coverUrl, setCoverUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (userId === null) return;
    setLoading(true);
    try {
      const headers: Record<string, string> = {};
      if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

      const url = `/api/v1/itch/status/${userId}`;
      const sResp = await fetch(url, { headers });
      if (!sResp.ok) throw new Error("Status fetch failed");
      const s = await sResp.json();

      setConnected(s.connected);
      if (s.connected) {
        setDisplayName(s.display_name || null);
        setCoverUrl(s.cover_url || null);
        const pResp = await fetch(
          `/api/v1/itch/profile/${userId}`,
          { headers },
        );
        if (pResp.ok) {
          const p = await pResp.json();
          setGames(p.owned_games || []);
        }
      } else {
        // Not connected (e.g. after disconnect) — clear cached data.
        setGames([]);
        setDisplayName(null);
        setCoverUrl(null);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to fetch itch.io data",
      );
    } finally {
      setLoading(false);
    }
  }, [userId, accessToken]);

  // Listen for itch:disconnected events from other components (e.g.
  // IntegrationsSection in settings) and re-fetch status so the UI
  // reflects the disconnected state.
  useEffect(() => {
    const handler = () => {
      if (userId !== null) {
        fetchData();
      }
    };
    window.addEventListener("itch:disconnected", handler);
    return () => window.removeEventListener("itch:disconnected", handler);
  }, [userId, fetchData]);

  useEffect(() => { fetchData(); }, [fetchData]);

  return { connected, loading, games, displayName, coverUrl, error };
}
