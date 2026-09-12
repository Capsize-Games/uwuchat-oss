import React from "react";
import { useTranslation } from "react-i18next";
import SteamGameCard from "./SteamGameCard";
import SteamStatsRow from "./SteamStatsRow";
import type { SteamGame, SteamProfile } from "../../../api/steam";
import styles from "./SteamDataSection.module.css";

type Tab = "recent" | "most_played";

interface SteamDataSectionProps {
  profile: SteamProfile;
}

export default function SteamDataSection({
  profile,
}: SteamDataSectionProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = React.useState<Tab>("recent");

  const TABS: { id: Tab; label: string; icon: string }[] = [
    { id: "recent", label: t("user.steam_data.tab_recent"), icon: "🕐" },
    { id: "most_played", label: t("user.steam_data.tab_most_played"), icon: "⭐" },
  ];

  const gamesToShow: SteamGame[] =
    activeTab === "recent"
      ? profile.recently_played.slice(0, 20)
      : [...profile.owned_games]
          .sort(
            (a, b) =>
              b.playtime_forever_minutes - a.playtime_forever_minutes,
          )
          .slice(0, 20);

  return (
    <>
      <div className={styles.tabBar}>
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={
                isActive ? styles.tabBtnActive : styles.tabBtnInactive
              }
            >
              {tab.icon} {tab.label}
            </button>
          );
        })}
      </div>

      <div className={styles.content}>
        {gamesToShow.length === 0 ? (
          <div className={styles.empty}>
            {activeTab === "recent"
              ? t("user.steam_data.no_recent")
              : t("user.steam_data.no_games")}
          </div>
        ) : (
          <div className={styles.gameScroll}>
            {gamesToShow.map((game) => (
              <SteamGameCard key={game.appid} game={game} />
            ))}
          </div>
        )}
      </div>

      <div className={styles.statsRow}>
        <SteamStatsRow
          steamLevel={profile.steam_level}
          totalGames={profile.total_games_owned}
          totalPlaytimeMinutes={profile.total_playtime_minutes}
          friendCount={profile.friend_count}
          personaState={profile.persona_state}
        />
      </div>
    </>
  );
}
