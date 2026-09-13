import React from "react";
import { useTranslation } from "react-i18next";
import styles from "./SteamNotConnected.module.css";

interface SteamNotConnectedProps {
  displayName: string;
  isOwnProfile: boolean;
  onConnect?: () => void;
  statusMessage?: string;
}

export default function SteamNotConnected({
  displayName,
  isOwnProfile,
  onConnect,
  statusMessage,
}: SteamNotConnectedProps) {
  const { t } = useTranslation();
  const isImporting =
    statusMessage === "scraping" || statusMessage === "pending";

  if (isImporting) {
    return (
      <div className={styles.wrap}>
        <div className={styles.importing}>
          {t("user.steam_not_connected.importing")}
        </div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.icon}>{"🎮"}</div>
        <div
          className={styles.message}
          // eslint-disable-next-line no-restricted-syntax -- state-driven conditional style
          style={{ marginBottom: isOwnProfile ? 16 : 0 }}
        >
          {isOwnProfile
            ? t("user.steam_not_connected.connect_own")
            : t("user.steam_not_connected.not_linked", { name: displayName })}
        </div>
        {isOwnProfile && onConnect && (
          <button onClick={onConnect} className={styles.connectBtn}>
            {t("user.steam_not_connected.connect_steam")}
          </button>
        )}
      </div>
    </div>
  );
}
