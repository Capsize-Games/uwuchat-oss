import { useEffect, useState, useCallback } from "react";
import LucideIcon from "@/components/shared/LucideIcon";
import { useAuth } from "../../hooks/useAuth";
import { getRequestHeaders } from "virtual:extensions";
import styles from "./FastSearchIndicator.module.css";

interface Status { healthy: boolean; error: string | null; response_time_ms: number | null; }

async function fetchHealth(): Promise<Status> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  try { const ext = getRequestHeaders(); if (ext["Authorization"]) headers["Authorization"] = ext["Authorization"]; } catch {}
  const resp = await fetch("/api/v1/fastsearch/status", { headers });
  if (!resp.ok) return { healthy: false, error: `HTTP ${resp.status}`, response_time_ms: null };
  return resp.json();
}

export default function FastSearchIndicator() {
  const { user } = useAuth();
  const isSuperuser = user?.is_superuser === true;
  const [status, setStatus] = useState<Status>({ healthy: true, error: null, response_time_ms: null });
  const fetch = useCallback(async () => { try { setStatus(await fetchHealth()); } catch {} }, []);
  useEffect(() => { fetch(); const t = setInterval(fetch, 30000); return () => clearInterval(t); }, [fetch]);
  if (!isSuperuser) return null;
  const color = status.healthy ? "#4caf50" : "#f44336";
  const tooltip = status.healthy ? `FastSearch OK (${status.response_time_ms}ms)` : `FastSearch: ${status.error || "unhealthy"}`;
  // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
  return <div className={styles.dot} style={{ background: color }} title={tooltip} />;
}
