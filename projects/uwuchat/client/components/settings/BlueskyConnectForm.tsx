import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { connectBluesky } from "../../api/bluesky";
import { SettingsButton } from "./SettingsButton";
import sectionStyles from "./sections/IntegrationsSection.module.css";
import styles from "./BlueskyConnectForm.module.css";

interface Props {
  userId: number;
  onConnected: () => void;
  onCancel: () => void;
}

export default function BlueskyConnectForm({
  userId,
  onConnected,
  onCancel,
}: Props) {
  const { t } = useTranslation();
  const [connecting, setConnecting] = useState(false);
  const [handle, setHandle] = useState("");
  const [appPassword, setAppPassword] = useState("");
  const [connectError, setConnectError] = useState<string | null>(null);

  const handleConnect = useCallback(async () => {
    if (!userId || !handle.trim() || !appPassword.trim()) return;
    setConnecting(true);
    setConnectError(null);
    try {
      await connectBluesky(userId, handle.trim(), appPassword.trim());
      onConnected();
    } catch (err) {
      setConnectError(
        err instanceof Error ? err.message : "Connection failed",
      );
    } finally {
      setConnecting(false);
    }
  }, [userId, handle, appPassword, onConnected]);

  return (
    <div className={sectionStyles.inlineForm}>
      <div className={sectionStyles.inlineFormTitle}>
        {t("settings.integrations.connect_bluesky")}
      </div>
      <div className={sectionStyles.inlineFormHint}>
        {t("settings.integrations.bluesky_app_password_hint")}
      </div>
      <input
        type="text"
        placeholder={t("settings.integrations.bluesky_handle_placeholder")}
        value={handle}
        onChange={(e) => setHandle(e.target.value)}
        className={styles.input}
      />
      <input
        type="password"
        placeholder={t("settings.integrations.bluesky_placeholder")}
        value={appPassword}
        onChange={(e) => setAppPassword(e.target.value)}
        className={styles.input}
      />
      {connectError && (
        <div className={styles.errorText}>
          {connectError}
        </div>
      )}
      <div className={styles.btnRow}>
        <SettingsButton
          variant="primary"
          onClick={handleConnect}
          disabled={connecting || !handle.trim() || !appPassword.trim()}
        >
          {connecting ? t("settings.integrations.bluesky_connecting") : t("settings.integrations.connect_bluesky")}
        </SettingsButton>
        <SettingsButton variant="secondary" onClick={onCancel}>
          {t("common.cancel")}
        </SettingsButton>
      </div>
    </div>
  );
}
