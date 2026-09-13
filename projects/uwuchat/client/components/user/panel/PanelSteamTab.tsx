import React, { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import type {
  SteamProfile,
  SteamAchievementsData,
} from "../../../api/steam";
import type { ItchioGame } from "../../../api/itchio";
import { getSteamAchievements } from "../../../api/steam";
import SteamGameLibrary from "../steam/SteamGameLibrary";
import { SettingsButton } from "../../settings/SettingsButton";
import { useIsMobile } from "../../../hooks/useIsMobile";
import ServiceIcon from "../../../data/socialIcons";
import styles from "./PanelSteamTab.module.css";

interface PanelSteamTabProps {
  steamConnected: boolean;
  steamLoading: boolean;
  steamProfile: SteamProfile | null;
  onConnect: () => void;
  itchConnected?: boolean;
  itchGames?: ItchioGame[];
  itchDisplayName?: string | null;
  itchCoverUrl?: string | null;
  onConnectItch?: () => void;
  compact?: boolean;
}

interface ViewingGameHeaderProps {
  game: { icon_url: string; name: string } | undefined;
  gameName: string | undefined;
  achievedCount: number;
  totalCount: number;
  onBack: () => void;
  thumbSize: number;
}

function ViewingGameHeader({
  game,
  gameName,
  achievedCount,
  totalCount,
  onBack,
  thumbSize,
}: ViewingGameHeaderProps) {
  return (
    <div className={styles.viewingHeader}>
      {game?.icon_url && (
        <img
          src={game.icon_url}
          alt=""
          className={styles.avatarThumb}
          // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
          style={{ width: thumbSize, height: thumbSize }}
        />
      )}
      <div className={styles.viewingHeaderInfo}>
        <span
          className={styles.viewingHeaderTitle}
        >
          {gameName || game?.name || "Game"} achievements
        </span>
        <div className={styles.viewingHeaderSub}>
          {achievedCount} / {totalCount} unlocked
        </div>
        <button
          onClick={onBack}
          className={styles.viewingHeaderBack}
        >
          ← Back to library
        </button>
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.sectionLabel}>
      {children}
    </div>
  );
}

const PERSONA_LABEL: Record<number, string> = {
  0: "Offline",
  1: "Online",
  2: "Busy",
  3: "Away",
  4: "Snooze",
  5: "Looking to Trade",
  6: "Looking to Play",
};

export default function PanelSteamTab({
  steamConnected,
  steamLoading,
  steamProfile,
  onConnect,
  itchConnected = false,
  itchGames = [],
  itchDisplayName = null,
  itchCoverUrl = null,
  onConnectItch,
  compact = false,
}: PanelSteamTabProps) {
  const [viewingAppid, setViewingAppid] = useState<number | null>(null);
  const [achievements, setAchievements] =
    useState<SteamAchievementsData | null>(null);
  const [achLoading, setAchLoading] = useState(false);
  const [achError, setAchError] = useState<string | null>(null);
  const { t } = useTranslation();
  const isMobile = useIsMobile();

  const thumbSize = compact ? 18 : 28;

  const fetchAchievements = useCallback(
    async (appid: number, userId: number) => {
      setViewingAppid(appid);
      setAchLoading(true);
      setAchError(null);
      setAchievements(null);
      try {
        const data = await getSteamAchievements(userId, appid);
        if (data.error) {
          setAchError(data.error);
        } else {
          setAchievements(data);
        }
      } catch (e: unknown) {
        setAchError(
          e instanceof Error
            ? e.message
            : "Failed to load achievements.",
        );
      } finally {
        setAchLoading(false);
      }
    },
    [],
  );

  const handleBack = useCallback(() => {
    setViewingAppid(null);
    setAchievements(null);
    setAchError(null);
  }, []);

  if (steamLoading) {
    return (
      <div className={styles.loadingBlock}>
        Loading Steam data&hellip;
      </div>
    );
  }

  if (!steamConnected) {
    if (itchConnected && itchGames.length > 0) {
      return (
        <div>
          {itchDisplayName && (
            <div
              className="d-flex gap-2 align-items-center mb-3"
            >
              {itchCoverUrl && (
                <img
                  src={itchCoverUrl} alt=""
                  className={styles.itchCoverThumb}
                  // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
                  style={{ width: thumbSize, height: thumbSize }}
                />
              )}
              <span className={styles.profileNameFull}>
                itch.io: {itchDisplayName}
              </span>
            </div>
          )}
          <SectionLabel>itch.io Games ({itchGames.length})</SectionLabel>
          <SteamGameLibrary games={itchGames} compact={compact} />
          <div className={styles.connectSection}>
            <SettingsButton
              variant="primary"
              className="w-100" onClick={onConnect}
            >
              <ServiceIcon serviceKey="steam" size={16} />
              Connect Steam
            </SettingsButton>
          </div>
        </div>
      );
    }

    return (
      <div>
        <SettingsButton
          variant="primary"
          className="w-100 mb-2" onClick={onConnect}
        >
          <ServiceIcon serviceKey="steam" size={16} />
          Connect Steam
        </SettingsButton>
        {!itchConnected && (
          <SettingsButton
            variant="primary"
            className="w-100" onClick={onConnectItch}
          >
            <ServiceIcon serviceKey="itchio" size={16} />
            Connect itch.io
          </SettingsButton>
        )}
      </div>
    );
  }

  if (!steamProfile) {
    return (
      <div className={styles.centeredBlock}>
        <div className={styles.steamIcon}>🎮</div>
        Steam account connected.
        <br />
        Profile data is syncing — check back shortly.
      </div>
    );
  }

  const recentGames = steamProfile.recently_played || [];
  const allGames = steamProfile.all_games || [];
  const mergedGames = [...allGames, ...(itchGames || [])];

  return (
    <div className={styles.connectedRoot}>
      {/* Fixed top block — header, stats, recently played. Only the
          game library / achievements list below scrolls. */}
      <div className={styles.fixedTop}>
      {/* Profile Header */}
      <div className={styles.profileHeader}>
        <img
          src={steamProfile.avatar_url || undefined}
          alt={steamProfile.display_name}
          className={styles.avatarThumb}
          // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
          style={{ width: thumbSize, height: thumbSize }}
        />
        <div className={styles.profileInfo}>
          {compact ? (
            <div className={styles.profileNameCompact}>
              <span className={styles.profileNameCompactText}>
                Steam: {steamProfile.display_name}
              </span>
              <span className={styles.profileNameCompactSecondary}>
                {" · "}Level {steamProfile.steam_level ?? "—"}
                {steamProfile.persona_state != null && (
                  <> · {PERSONA_LABEL[steamProfile.persona_state] || "Online"}</>
                )}
              </span>
            </div>
          ) : (
            <>
              <div className={styles.profileNameFull}>
                Steam: {steamProfile.display_name}
              </div>
              <div className={styles.profileSub}>
                Level {steamProfile.steam_level ?? "—"}
                {steamProfile.persona_state != null && (
                  <> · {PERSONA_LABEL[steamProfile.persona_state] || "Online"}</>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* itch.io Profile */}
      {itchConnected && itchDisplayName && (
        <div className={styles.itchRow}>
          {itchCoverUrl && (
            <img src={itchCoverUrl} alt=""
              className={styles.itchCoverThumb}
              // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
              style={{ width: thumbSize, height: thumbSize }} />
          )}
          <span className={styles.itchName}>
            itch.io: {itchDisplayName}
          </span>
        </div>
      )}

      {/* Stats */}
      <SectionLabel>{t("user.steam.section_stats")}</SectionLabel>
      <div className={styles.statsGrid}>
        {([
          [steamProfile.total_games_owned ?? "—", t("user.steam.stat_games")],
          [steamProfile.total_playtime_minutes != null
            ? Math.round(steamProfile.total_playtime_minutes / 60)
                .toLocaleString()
            : "—", t("user.steam.stat_hours")],
          [steamProfile.friend_count ?? "—", t("user.steam.friends")],
          [steamProfile.steam_level ?? "—", t("user.steam.steam_level")],
        ] as const).map(([value, label]) => (
          <div key={label} className={styles.statCard}>
            <div className={styles.statValue}>{value}</div>
            <div className={styles.statLabel}>{label}</div>
          </div>
        ))}
      </div>

      {/* Recently Played — hidden on mobile; the panel is narrow
          enough there that it's redundant with the game library. */}
      {!isMobile && recentGames.length > 0 && (
        <>
          <SectionLabel>{t("user.steam.section_recently_played")}</SectionLabel>
          {recentGames.slice(0, 5).map((game) => (
            <div key={game.appid} className={styles.recentGame}>
              {game.icon_url ? (
                <img src={game.icon_url} alt="" loading="lazy"
                  className={styles.recentGameIcon}
                  // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
                  style={{ width: thumbSize, height: thumbSize }} />
              ) : (
                <div className={styles.recentGamePlaceholder}
                  // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
                  style={{ width: thumbSize, height: thumbSize }} />
              )}
              <div className={styles.recentGameName}>
                {game.name}
              </div>
              <div className={styles.recentGameHours}>
                {Math.round((game.playtime_2weeks_minutes ?? 0) / 60)}h
              </div>
            </div>
          ))}
        </>
      )}

      {/* Separator */}
      {!isMobile && recentGames.length > 0 && allGames.length > 0 && (
        <div className={styles.separator} />
      )}
      </div>

      {/* Game Library or Achievements — the only scrolling region;
          the section label (and the library's search bar) stay fixed. */}
      {allGames.length > 0 && (
        <div className={styles.librarySection}>
          <div className={styles.libraryHeader}>
            <SectionLabel>
              {viewingAppid != null ? (
                <ViewingGameHeader
                  game={allGames.find(
                    (g) => g.appid === viewingAppid,
                  )}
                  gameName={achievements?.game_name}
                  achievedCount={achievements?.achieved_count ?? 0}
                  totalCount={achievements?.total_count ?? 0}
                  onBack={handleBack}
                  thumbSize={thumbSize}
                />
              ) : (
                <>Game Library ({mergedGames.length})</>
              )}
            </SectionLabel>
          </div>

          {viewingAppid == null ? (
            <SteamGameLibrary
              games={mergedGames} compact={compact} fillHeight
              onGameClick={(appid) =>
                fetchAchievements(appid, steamProfile.user_id)
              }
            />
          ) : achLoading ? (
            <div className={styles.achLoading}>
              Loading achievements&hellip;
            </div>
          ) : achError ? (
            <div className={styles.achError}>
              {achError}
            </div>
          ) : achievements ? (
            achievements.total_count === 0 ? (
              <div className={styles.achEmpty}>
                This game has no achievements.
              </div>
            ) : (
              <div className={styles.achList}>
                  {achievements.achievements.map((ach) => (
                    <div key={ach.apiname}
                      className={`${styles.achItem} ${ach.achieved ? styles.achItemBright : styles.achItemDim}`}
                    >
                      {/* Achievement icon */}
                      {ach.icon_url ? (
                        <img
                          src={ach.achieved ? ach.icon_url : ach.icon_gray_url}
                          alt=""
                          loading="lazy"
                          className={styles.achIcon}
                        />
                      ) : (
                        <div className={styles.achPlaceholder} />
                      )}
                      <div className={styles.achInfo}>
                        <div className={ach.achieved ? styles.achNameAchieved : styles.achNameUnachieved}>
                          {ach.name}
                        </div>
                        <div className={styles.achDesc}>
                          {ach.description}
                        </div>
                      </div>
                      {ach.global_percent != null && (
                        <div className={styles.achPercent}
                          title={`${Number(ach.global_percent).toFixed(1)}%
                            of players`}>
                          {Number(ach.global_percent).toFixed(1)}%
                        </div>
                      )}
                    </div>
                  ))}
              </div>
            )
          ) : null}
        </div>
      )}
    </div>
  );
}
