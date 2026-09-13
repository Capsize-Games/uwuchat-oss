import React from "react";
import { useTranslation } from "react-i18next";
import StatBadge from "../shared/StatBadge";
import styles from "./SteamStatsRow.module.css";

interface SteamStatsRowProps {
  steamLevel: number;
  totalGames: number;
  totalPlaytimeMinutes: number;
  friendCount: number;
  personaState: number;
}

const PERSONA_LABELS: Record<number, string> = {
  0: "Offline",
  1: "Online",
  2: "Busy",
  3: "Away",
  4: "Snooze",
  5: "Looking to Trade",
  6: "Looking to Play",
};

function formatHours(minutes: number): number {
  return Math.round(minutes / 60);
}

export default function SteamStatsRow({
  steamLevel,
  totalGames,
  totalPlaytimeMinutes,
  friendCount,
  personaState,
}: SteamStatsRowProps) {
  const { t } = useTranslation();
  const onlineLabel =
    personaState > 0 ? PERSONA_LABELS[personaState] ?? null : null;

  return (
    <div className={styles.row}>
      <StatBadge label={t("user.steam_stats.steam_level")} value={steamLevel} />
      <StatBadge label={t("user.steam_stats.games_owned")} value={totalGames} />
      <StatBadge
        label={t("user.steam_stats.total_hours")}
        value={formatHours(totalPlaytimeMinutes)}
      />
      <StatBadge label={t("user.steam_stats.friends")} value={friendCount} />
      {onlineLabel && (
        <span className={styles.onlineBadge}>
          {onlineLabel}
        </span>
      )}
    </div>
  );
}
