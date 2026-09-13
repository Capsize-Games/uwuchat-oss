/**
 * FastSearch admin status panel — rendered in the right sidebar of ChatView.
 * Includes health status, metrics, server controls, and logs.
 */
import { useCallback, useEffect, useState } from "react";
import LucideIcon from "@/components/shared/LucideIcon";
import { getRequestHeaders } from "virtual:extensions";
import styles from "./FastSearchStatusPanel.module.css";

/* ── Types ── */

interface FastSearchStatus {
  configured: boolean;
  base_url: string;
  healthy: boolean;
  error: string | null;
  response_time_ms: number | null;
  last_success_at: string | null;
  cache_stats: Record<string, number> | null;
}

interface TestResult {
  success: boolean;
  message: string;
  result_count: number;
  elapsed_ms: number;
  error: string | null;
}

interface SSHResult {
  success: boolean;
  message: string;
  stdout: string | null;
  stderr: string | null;
}

interface LogsData {
  lines: string[];
  truncated: boolean;
}

/* ── API ── */

const API_BASE = "/api/v1/fastsearch";

async function apiFetch<T>(
  method: string,
  path: string,
  body?: Record<string, unknown>,
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  try {
    const extHeaders = getRequestHeaders();
    if (extHeaders["Authorization"]) headers["Authorization"] = extHeaders["Authorization"];
  } catch { /* unavailable */ }
  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status}: ${text}`);
  }
  return resp.json();
}

async function fetchStatus(): Promise<FastSearchStatus> {
  return apiFetch<FastSearchStatus>("GET", "/status");
}
async function runTest(): Promise<TestResult> {
  return apiFetch<TestResult>("POST", "/test");
}
async function restartServer(): Promise<SSHResult> {
  return apiFetch<SSHResult>("POST", "/restart");
}
async function rebuildServer(): Promise<SSHResult> {
  return apiFetch<SSHResult>("POST", "/rebuild");
}
async function fetchLogs(): Promise<LogsData> {
  return apiFetch<LogsData>("GET", "/logs");
}

export default function FastSearchStatusPanel() {
  const [status, setStatus] = useState<FastSearchStatus | null>(null);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [logs, setLogs] = useState<LogsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const s = await fetchStatus();
      setStatus(s);
    } catch { /* keep last */ }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadStatus();
    const timer = setInterval(loadStatus, 30000);
    return () => clearInterval(timer);
  }, [loadStatus]);

  const handleTest = async () => {
    setActionLoading("test");
    try {
      const r = await runTest();
      setTestResult(r);
      if (r.success) await loadStatus();
    } finally { setActionLoading(null); }
  };

  const handleRestart = async () => {
    if (!window.confirm("Restart the FastSearch web container?")) return;
    setActionLoading("restart");
    try {
      const r = await restartServer();
      setTestResult({ success: r.success, message: r.message, result_count: 0, elapsed_ms: 0, error: r.stderr });
      await loadStatus();
    } finally { setActionLoading(null); }
  };

  const handleRebuild = async () => {
    if (!window.confirm("Rebuild and redeploy FastSearch? This may take several minutes.")) return;
    setActionLoading("rebuild");
    try {
      const r = await rebuildServer();
      setTestResult({ success: r.success, message: r.message, result_count: 0, elapsed_ms: 0, error: r.stderr });
      await loadStatus();
    } finally { setActionLoading(null); }
  };

  const handleLogs = async () => {
    setActionLoading("logs");
    try {
      const l = await fetchLogs();
      setLogs(l);
    } finally { setActionLoading(null); }
  };

  const handleCopyPrompt = async () => {
    const lines: string[] = [
      "The FastSearch server is unhealthy. Please diagnose and fix it.",
      "",
      "=== Status ===",
      `Base URL: ${status?.base_url ?? "unknown"}`,
      `Healthy: ${status?.healthy ? "yes" : "NO"}`,
      `Error: ${status?.error ?? "none"}`,
      `Response Time: ${status?.response_time_ms != null ? `${status.response_time_ms}ms` : "N/A"}`,
      `Last Success: ${status?.last_success_at ?? "Never"}`,
      `Configured: ${status?.configured ? "yes" : "no"}`,
      "",
      "=== Recent Logs ===",
      ...(logs?.lines?.slice(-15) ?? ["No logs loaded — click View Logs first"]),
      "",
      "=== Connection ===",
      `Connection: ${status?.healthy ? "Reachable" : "Unreachable"}`,
      "",
      "Please fix the FastSearch server and confirm it returns healthy.",
    ];
    await navigator.clipboard.writeText(lines.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 3000);
  };

  return (
    <div className={styles.panel}>
      {/* Status */}
      <div className={styles.section}>
        <div className={styles.headerRow}>
          <div>
            {loading ? (
              <span className={styles.checking}>Checking...</span>
            ) : status ? (
              <div className={styles.statusRow}>
                <LucideIcon
                  name={status.healthy ? "globe-check" : "globe-off"}
                  size={16}
                  color={status.healthy ? "#4caf50" : "#f44336"}
                  className="me-2"
                />
                <span className={status.healthy ? styles.statusHealthy : styles.statusUnhealthy}>
                  {status.healthy ? "Healthy" : "Unhealthy"}
                </span>
              </div>
            ) : (
              <span className={styles.unable}>Unable to reach</span>
            )}
            {status?.error && <div className={styles.error}>{status.error}</div>}
          </div>
          <div>
            <button className={styles.btn} onClick={handleTest} disabled={actionLoading === "test"}>
              {actionLoading === "test" && <span className={styles.spinner} />}
              Test
            </button>
            <button className={styles.btn} onClick={loadStatus}>↻</button>
          </div>
        </div>

        {status && (
          <div className={styles.metricsGrid}>
            <Metric label="Configured" value={status.configured ? "Yes" : "No"} />
            <Metric label="Base URL" value={status.base_url} />
            <Metric label="Response Time" value={status.response_time_ms != null ? `${status.response_time_ms}ms` : "N/A"} />
            <Metric label="Last Success" value={status.last_success_at ? new Date(status.last_success_at).toLocaleString() : "Never"} />
          </div>
        )}

        {testResult && (
          <div className={testResult.success ? styles.testSuccess : styles.testFailure}>
            <div className={testResult.success ? styles.testMsgSuccess : styles.testMsgFailure}>
              {testResult.message}
            </div>
            {testResult.success && (
              <div className={styles.testMeta}>
                {testResult.result_count} results in {testResult.elapsed_ms}ms
              </div>
            )}
          </div>
        )}
      </div>

      {/* Controls */}
      <div className={styles.section}>
        <div className={styles.labelMb8}>Server Controls</div>
        <button className={styles.dangerBtn} onClick={handleRestart} disabled={actionLoading === "restart"}>
          {actionLoading === "restart" && <span className={styles.spinner} />}
          Restart
        </button>
        <button className={styles.dangerBtn} onClick={handleRebuild} disabled={actionLoading === "rebuild"}>
          {actionLoading === "rebuild" && <span className={styles.spinner} />}
          Rebuild
        </button>
        <button className={styles.btn} onClick={handleLogs} disabled={actionLoading === "logs"}>
          {actionLoading === "logs" && <span className={styles.spinner} />}
          Logs
        </button>
        <button className={styles.aiBtn} onClick={handleCopyPrompt}>
          🤖 Copy Prompt
        </button>
        {copied && <span className={styles.copied}>Copied!</span>}
      </div>

      {/* Logs */}
      {logs && (
        <div className={styles.sectionLast}>
          <div className={styles.labelMb6}>Server Logs {logs.truncated ? "" : "(truncated)"}</div>
          <div className={styles.logArea}>
            {logs.lines.length === 0
              ? "No log entries found."
              : logs.lines.map((line, i) => <div key={i}>{line}</div>)}
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className={styles.metricLabel}>{label}</div>
      <div className={styles.metricValue}>{value || "N/A"}</div>
    </div>
  );
}
