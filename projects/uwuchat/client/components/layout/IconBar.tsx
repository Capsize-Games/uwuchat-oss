import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import LucideIcon from "@/components/shared/LucideIcon";
import styles from "./IconBar.module.css";
import { useAuth } from "../../hooks/useAuth";
import { BottomBar as AuthBottomBar } from "@extensions/auth/client/BottomBar";
import { useDeployment } from "@/context/DeploymentContext";
import { getRequestHeaders } from "virtual:extensions";
import type { ReactNode } from "react";

interface FastSearchStatus {
  healthy: boolean;
  error: string | null;
  response_time_ms: number | null;
}

async function fetchFastSearchHealth(): Promise<FastSearchStatus> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  try {
    const extHeaders = getRequestHeaders();
    if (extHeaders["Authorization"]) {
      headers["Authorization"] = extHeaders["Authorization"];
    }
  } catch {
    /* unavailable */
  }
  const resp = await fetch("/api/v1/fastsearch/status", { headers });
  if (!resp.ok)
    return { healthy: false, error: `HTTP ${resp.status}`, response_time_ms: null };
  return resp.json();
}

type PanelId = "civitai_browser";

export function LeftIconBar({
  onOpenSettings,
  bottomSlot: _bottomSlot,
}: {
  showChat: boolean;
  showCanvas: boolean;
  rightPanel: PanelId | null;
  onToggleChat: () => void;
  onToggleCanvas: () => void;
  onRightPanel: (id: PanelId) => void;
  onOpenSettings: () => void;
  bottomSlot?: ReactNode;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const isSuperuser = user?.is_superuser === true;
  const openAdminUsers = () => {
    window.dispatchEvent(new Event("airunner:show-admin-users"));
  };

  // ── Cloud mode toggle ──────────────────────────────────────
  const { deployment, setDeployment } = useDeployment();
  const isCloud = deployment === "cloud";
  const toggleCloudMode = () => {
    setDeployment(isCloud ? "edge" : "cloud");
  };

  // ── Inspection toggle ──────────────────────────────────────
  const [inspectionOn, setInspectionOn] = useState(false);
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ enabled: boolean }>).detail;
      if (detail && typeof detail.enabled === "boolean") {
        setInspectionOn(detail.enabled);
      }
    };
    window.addEventListener("airunner:inspection-changed", handler);
    return () =>
      window.removeEventListener("airunner:inspection-changed", handler);
  }, []);
  const toggleInspection = () => {
    window.dispatchEvent(new Event("airunner:toggle-inspection"));
  };

  // ── FastSearch health ────────────────────────────────────
  const [fsStatus, setFsStatus] = useState<FastSearchStatus>({
    healthy: true,
    error: null,
    response_time_ms: null,
  });

  const checkFsHealth = useCallback(async () => {
    try {
      const s = await fetchFastSearchHealth();
      setFsStatus(s);
    } catch {
      /* keep last status */
    }
  }, []);

  useEffect(() => {
    if (!isSuperuser) return;
    checkFsHealth();
    const timer = setInterval(checkFsHealth, 60000);
    return () => clearInterval(timer);
  }, [isSuperuser, checkFsHealth]);

  const openFastSearchPanel = () => {
    window.dispatchEvent(new Event("airunner:show-fastsearch-status"));
  };

  return (
    <div className="icon-bar left">
      <div className={styles.homeWrap}>
        <button
          type="button"
          onClick={() =>
            window.dispatchEvent(new Event("uwuchat:toggle-contacts"))
          }
          title={t("iconbar.home")}
          className={styles.homeBtn}
        >
          <LucideIcon name="bot-message-square" size={20} />
        </button>
      </div>

      <div className="flex-spacer" />

      {/* ── Superuser-only: Cloud mode ── */}
      {isSuperuser && (
        <button
          onClick={toggleCloudMode}
          title={isCloud
            ? "Cloud mode — click to switch to edge"
            : "Edge mode — click to switch to cloud"}
        >
          <LucideIcon
            name="cloud"
            size={16}
            color={isCloud ? "#4caf50" : "rgba(255,255,255,0.35)"}
          />
          <span className="icon-bar-label">{isCloud ? "Cloud" : "Edge"}</span>
        </button>
      )}

      {/* ── Superuser-only: Inspector ── */}
      {isSuperuser && (
        <button
          onClick={toggleInspection}
          title={inspectionOn
            ? "Inspection mode on — click to disable"
            : "Inspection mode off — click to enable"}
        >
          <LucideIcon
            name="scan-search"
            size={16}
            color={inspectionOn ? "#4caf50" : "rgba(255,255,255,0.35)"}
          />
          <span className="icon-bar-label">Inspect</span>
        </button>
      )}

      {/* ── Superuser-only: FastSearch status ── */}
      {isSuperuser && (
        <button
          onClick={openFastSearchPanel}
          title={fsStatus.healthy
            ? "FastSearch is healthy"
            : `FastSearch is unhealthy${fsStatus.error ? `: ${fsStatus.error}` : ""}`}
        >
          <LucideIcon
            name={fsStatus.healthy ? "globe-check" : "globe-off"}
            size={16}
            color={fsStatus.healthy ? "#4caf50" : "#f44336"}
          />
          <span className="icon-bar-label">Search</span>
        </button>
      )}

      {/* ── Superuser-only: Admin Users ── */}
      {isSuperuser && (
        <button
          onClick={openAdminUsers}
          title={t("iconbar.admin_users")}
        >
          <LucideIcon name="users" size={16} />
          <span className="icon-bar-label">{t("iconbar.users_label")}</span>
        </button>
      )}

      {/* ── Contacts (grouped with Account as primary nav) ── */}
      <button
        className="contacts-mobile-toggle"
        onClick={() => window.dispatchEvent(new Event("uwuchat:toggle-contacts"))}
        title={t("chat.contacts")}
      >
        <LucideIcon name="users" size={16} />
        <span className="icon-bar-label">{t("chat.contacts")}</span>
      </button>

      <AuthBottomBar />
    </div>
  );
}
