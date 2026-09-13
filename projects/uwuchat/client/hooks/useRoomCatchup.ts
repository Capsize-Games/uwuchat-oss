import { useState, useEffect } from "react";
import { request } from "../api/client-base";

const STORAGE_KEY = "room_last_viewed";
const CATCHUP_THRESHOLD_MS = 60 * 1000; // 1 minute (DEBUG)

function getLastViewed(roomId: number): string | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const map = raw ? (JSON.parse(raw) as Record<string, string>) : {};
    return map[String(roomId)] ?? null;
  } catch {
    return null;
  }
}

function setLastViewed(roomId: number): void {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const map = raw ? (JSON.parse(raw) as Record<string, string>) : {};
    map[String(roomId)] = new Date().toISOString();
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {}
}

async function fetchCatchup(roomId: number, since: string): Promise<string> {
  const result = await request<{ summary: string }>(
    "GET",
    `/api/v1/rooms/${roomId}/catch-up?since=${encodeURIComponent(since)}`,
  );
  return result.summary ?? "";
}

export function useRoomCatchup(roomId: number | null): {
  catchup: string | null;
  dismiss: () => void;
} {
  const [catchup, setCatchup] = useState<string | null>(null);

  useEffect(() => {
    if (roomId === null) return;

    const lastViewed = getLastViewed(roomId);
    setLastViewed(roomId);

    if (!lastViewed) return;

    const gap = Date.now() - new Date(lastViewed).getTime();
    if (gap < CATCHUP_THRESHOLD_MS) return;

    let cancelled = false;
    fetchCatchup(roomId, lastViewed)
      .then((summary) => {
        if (!cancelled && summary) setCatchup(summary);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [roomId]);

  function dismiss() {
    setCatchup(null);
  }

  return { catchup, dismiss };
}
