import React from "react";
import type { SteamGame } from "../../../api/steam";
import styles from "./SteamGameCard.module.css";

interface SteamGameCardProps {
  game: SteamGame;
}

function formatHours(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.round(minutes / 60);
  if (h < 1000) return `${h}h`;
  return `${(h / 1000).toFixed(1)}k h`;
}

export default function SteamGameCard({ game }: SteamGameCardProps) {
  return (
    <div className={styles.card}>
      <div className={styles.imageWrap}>
        {game.store_header_url && (
          <img
            src={game.store_header_url}
            alt={game.name}
            className={styles.image}
            loading="lazy"
          />
        )}
      </div>
      <div className={styles.info}>
        <div className={styles.name} title={game.name}>
          {game.name}
        </div>
        <div className={styles.playtime}>
          {formatHours(game.playtime_forever_minutes)}
          {game.playtime_2weeks_minutes != null &&
            game.playtime_2weeks_minutes > 0 && (
              <span className={styles.recentBadge}>
                +{formatHours(game.playtime_2weeks_minutes)} recent
              </span>
            )}
        </div>
      </div>
    </div>
  );
}
