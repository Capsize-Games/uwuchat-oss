import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../hooks/useAuth";
import { SteamIcon } from "../icons/SteamIcon";
import { ItchIcon } from "../icons/ItchIcon";
import { BlueskyIcon } from "../icons/BlueskyIcon";
import {
  getSteamAuthUrl,
  getSteamStatus,
  disconnectSteam,
} from "../../../api/steam";
import {
  getItchAuthUrl,
  getItchStatus,
  disconnectItch,
} from "../../../api/itchio";
import {
  getBlueskyStatus,
  disconnectBluesky,
} from "../../../api/bluesky";
import { IntegrationCard } from "../IntegrationCard";
import BlueskyConnectForm from "../BlueskyConnectForm";
import styles from "./IntegrationsSection.module.css";

// ── Component ────────────────────────────────────────────────────────────

export default function IntegrationsSection() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const userId = user?.id ?? 0;

  // ── Redirect-param cleanup (on mount) ───────────────────────────────

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    let changed = false;
    for (const key of [
      "steam_connected",
      "steam_error",
      "itch_connected",
      "itch_error",
    ]) {
      if (params.has(key)) {
        params.delete(key);
        changed = true;
      }
    }
    if (changed) {
      const url = new URL(location.href);
      url.search = params.toString();
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  // ── Steam ─────────────────────────────────────────────────────────────

  const [steamConnecting, setSteamConnecting] = useState(false);
  const [steamConnected, setSteamConnected] = useState(false);
  const [steamStatus, setSteamStatus] = useState<string | null>(null);
  const [steamLoading, setSteamLoading] = useState(true);
  const [steamDisconnecting, setSteamDisconnecting] = useState(false);
  const [steamAuthProvider, setSteamAuthProvider] = useState<string | null>(null);

  const fetchSteamStatus = useCallback(() => {
    if (!userId) {
      setSteamLoading(false);
      return;
    }
    setSteamLoading(true);
    getSteamStatus(userId)
      .then((status) => {
        setSteamConnected(status.connected);
        setSteamStatus(status.status);
        setSteamAuthProvider(status.auth_provider ?? null);
      })
      .catch(() => {
        setSteamConnected(false);
      })
      .finally(() => setSteamLoading(false));
  }, [userId]);

  useEffect(() => {
    fetchSteamStatus();
  }, [fetchSteamStatus]);

  const handleConnectSteam = useCallback(async () => {
    try {
      setSteamConnecting(true);
      const url = await getSteamAuthUrl();
      window.location.href = url;
    } catch {
      setSteamConnecting(false);
    }
  }, []);

  const handleDisconnectSteam = useCallback(async () => {
    if (!userId) return;
    try {
      setSteamDisconnecting(true);
      await disconnectSteam(userId);
      setSteamConnected(false);
      setSteamStatus(null);
      window.dispatchEvent(new CustomEvent("steam:disconnected"));
    } catch {
      // ignore
    } finally {
      setSteamDisconnecting(false);
    }
  }, [userId]);

  const steamStatusText =
    steamStatus === "error" ? "Connection error" : null;

  // ── itch.io ────────────────────────────────────────────────────────────

  const [itchConnecting, setItchConnecting] = useState(false);
  const [itchConnected, setItchConnected] = useState(false);
  const [itchLoading, setItchLoading] = useState(true);
  const [itchDisconnecting, setItchDisconnecting] = useState(false);

  useEffect(() => {
    if (!userId) {
      setItchLoading(false);
      return;
    }
    setItchLoading(true);
    getItchStatus(userId)
      .then((s) => {
        setItchConnected(s.connected);
      })
      .catch(() => {
        setItchConnected(false);
      })
      .finally(() => setItchLoading(false));
  }, [userId]);

  const handleConnectItch = useCallback(async () => {
    try {
      setItchConnecting(true);
      const url = await getItchAuthUrl();
      window.location.href = url;
    } catch {
      setItchConnecting(false);
    }
  }, []);

  const handleDisconnectItch = useCallback(async () => {
    if (!userId) return;
    try {
      setItchDisconnecting(true);
      await disconnectItch(userId);
      setItchConnected(false);
      window.dispatchEvent(new CustomEvent("itch:disconnected"));
    } catch {
      // ignore
    } finally {
      setItchDisconnecting(false);
    }
  }, [userId]);

  // ── Bluesky ─────────────────────────────────────────────────────────────

  const [showBlueskyForm, setShowBlueskyForm] = useState(false);
  const [blueskyConnected, setBlueskyConnected] = useState(false);
  const [blueskyLoading, setBlueskyLoading] = useState(true);
  const [blueskyDisconnecting, setBlueskyDisconnecting] = useState(false);

  const fetchBlueskyStatus = useCallback(() => {
    if (!userId) {
      setBlueskyLoading(false);
      return;
    }
    setBlueskyLoading(true);
    getBlueskyStatus(userId)
      .then((s) => {
        setBlueskyConnected(s.connected);
      })
      .catch(() => {
        setBlueskyConnected(false);
      })
      .finally(() => setBlueskyLoading(false));
  }, [userId]);

  useEffect(() => {
    fetchBlueskyStatus();
  }, [fetchBlueskyStatus]);

  const handleConnectBluesky = useCallback(() => {
    setShowBlueskyForm(true);
  }, []);

  const handleBlueskyConnected = useCallback(() => {
    setShowBlueskyForm(false);
    fetchBlueskyStatus();
  }, [fetchBlueskyStatus]);

  const handleBlueskyFormCancel = useCallback(() => {
    setShowBlueskyForm(false);
  }, []);

  const handleDisconnectBluesky = useCallback(async () => {
    if (!userId) return;
    try {
      setBlueskyDisconnecting(true);
      await disconnectBluesky(userId);
      setBlueskyConnected(false);
      window.dispatchEvent(new CustomEvent("bluesky:disconnected"));
    } catch {
      // ignore
    } finally {
      setBlueskyDisconnecting(false);
    }
  }, [userId]);

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div className={styles.wrap}>
      <h6 className="text-theme-secondary">{t("settings.integrations.title")}</h6>

      {/* Steam */}
      <IntegrationCard
        name="Steam"
        icon={<SteamIcon width={24} height={24} />}
        description={t("settings.integrations.steam_desc")}
        loading={steamLoading}
        connected={steamConnected}
        statusText={steamStatusText}
        connectedLabel={t("settings.integrations.connected_label_steam")}
        onConnect={handleConnectSteam}
        onDisconnect={handleDisconnectSteam}
        connecting={steamConnecting}
        disconnecting={steamDisconnecting}
        connectLabel={t("settings.integrations.connect_steam")}
        showDisconnect={steamAuthProvider !== "steam"}
      />

      {/* itch.io */}
      <IntegrationCard
        name="itch.io"
        icon={<ItchIcon width={24} height={24} />}
        description={t("settings.integrations.itch_desc")}
        loading={itchLoading}
        connected={itchConnected}
        connectedLabel={t("settings.integrations.connected_label_itch")}
        onConnect={handleConnectItch}
        onDisconnect={handleDisconnectItch}
        connecting={itchConnecting}
        disconnecting={itchDisconnecting}
        connectLabel={t("settings.integrations.connect_itch")}
      />

      {/* Bluesky */}
      {showBlueskyForm ? (
        <BlueskyConnectForm
          userId={userId}
          onConnected={handleBlueskyConnected}
          onCancel={handleBlueskyFormCancel}
        />
      ) : (
        <IntegrationCard
          name="Bluesky"
          icon={<BlueskyIcon width={24} height={24} />}
          description={t("settings.integrations.bluesky_desc")}
          loading={blueskyLoading}
          connected={blueskyConnected}
          connectedLabel={t("settings.integrations.connected_label_bluesky")}
          onConnect={handleConnectBluesky}
          onDisconnect={handleDisconnectBluesky}
          disconnecting={blueskyDisconnecting}
          connectLabel={t("settings.integrations.connect_bluesky")}
        />
      )}
    </div>
  );
}
