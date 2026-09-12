/**
 * FastSearch health indicator shown at the bottom of the left icon bar.
 *
 * Polls /api/v1/fastsearch/status every 60 seconds and shows a green/red
 * dot. Clicking opens a status panel in the chat sidebar. Only visible
 * to superusers.
 */

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@extensions/auth/client/Provider";
import LucideIcon from "@/components/shared/LucideIcon";
import { getRequestHeaders } from "virtual:extensions";

interface Status {
  healthy: boolean;
  error: string | null;
  response_time_ms: number | null;
}

async function fetchHealth(): Promise<Status> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  try {
    const extHeaders = getRequestHeaders();
    if (extHeaders["Authorization"]) {
      headers["Authorization"] = extHeaders["Authorization"];
    }
  } catch { /* unavailable */ }
  const resp = await fetch("/api/v1/fastsearch/status", { headers });
  if (!resp.ok) return { healthy: false, error: `HTTP ${resp.status}`, response_time_ms: null };
  return resp.json();
}

/* ── Component ── */

export function BottomBar() {
  const { user } = useAuth();
  const isSuperuser = user?.is_superuser === true;

  const [status, setStatus] = useState<Status>({ healthy: true, error: null, response_time_ms: null });

  const checkHealth = useCallback(async () => {
    try {
      const s = await fetchHealth();
      setStatus(s);
    } catch { /* keep last status */ }
  }, []);

  useEffect(() => {
    if (!isSuperuser) return;
    checkHealth();
    const timer = setInterval(checkHealth, 60000);
    return () => clearInterval(timer);
  }, [isSuperuser, checkHealth]);

  if (!isSuperuser) return null;

  const tooltip = status.healthy
    ? "FastSearch is healthy"
    : `FastSearch is unhealthy${status.error ? `: ${status.error}` : ""}`;

  const iconName = status.healthy ? "globe-check" : "globe-off";
  const iconColor = status.healthy ? "#4caf50" : "#f44336";
  const healthy = status.healthy;


  const openPanel = () => {
    window.dispatchEvent(new Event("airunner:show-fastsearch-status"));
  };

  return (
    <div style={{ padding: "8px 0", display: "flex", flexDirection: "column", alignItems: "center" }}>
      <button
        onClick={openPanel}
        title={tooltip}
        aria-label={tooltip}
        style={{
          border: "none",
          cursor: "pointer",
          padding: 4,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <LucideIcon name={iconName} size={18} color={iconColor} />
        <span className="icon-bar-label">FS Status</span>
      </button>
    </div>
  );
}
