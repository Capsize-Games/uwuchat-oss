import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { SteamGame } from "../../../api/steam";
import type { ItchioGame } from "../../../api/itchio";
import styles from "./SteamGameLibrary.module.css";

type GameEntry = SteamGame | ItchioGame;

interface Props {
  games: GameEntry[];
  compact?: boolean;
  fillHeight?: boolean;
  onGameClick?: (appid: number) => void;
}

function formatHours(minutes: number): string {
  const h = Math.round(minutes / 60);
  if (h < 1) return "< 1h";
  if (h >= 1000) return `${(h / 1000).toFixed(1)}kh`;
  return `${h.toLocaleString()}h`;
}

export default function SteamGameLibrary({
  games,
  compact = false,
  fillHeight = false,
  onGameClick,
}: Props) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const thumbSize = compact ? 18 : 28;

  const filtered = useMemo(() => {
    if (!search.trim()) return games;
    const q = search.toLowerCase();
    return games.filter((g) =>
      g.name.toLowerCase().includes(q),
    );
  }, [games, search]);

  if (games.length === 0) {
    return <div className={styles.empty}>{t("user.steam.no_games")}</div>;
  }

  const wrapClass = fillHeight ? styles.wrapFill : styles.wrap;
  const listClass = fillHeight ? styles.listFill : styles.listFixed;

  return (
    <div className={wrapClass}>
      <input
        type="text"
        placeholder={`Search ${games.length} games…`}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className={styles.searchInput}
      />

      <div className={listClass}>
        {filtered.map((game) => {
          const isSteam = !("source" in game);
          const clickable = isSteam && onGameClick != null;
          const rowClass = clickable
            ? styles.gameRowClickable
            : styles.gameRow;
          return (
            <div
              key={game.appid}
              onClick={
                clickable
                  ? () => onGameClick((game as SteamGame).appid)
                  : undefined
              }
              className={rowClass}
            >
              {game.icon_url ? (
                <img
                  src={game.icon_url}
                  alt=""
                  className={styles.gameIcon}
                  // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                  style={{
                    width: thumbSize,
                    height: thumbSize,
                  }}
                  loading="lazy"
                />
              ) : (
                <div
                  className={styles.gameIconFallback}
                  // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                  style={{
                    width: thumbSize,
                    height: thumbSize,
                  }}
                />
              )}
              <div className={styles.gameName}>
                {game.name}
              </div>
              <div className={styles.gameHours}>
                {formatHours(game.playtime_forever_minutes)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
