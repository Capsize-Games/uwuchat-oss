import React from "react";
import { useTranslation } from "react-i18next";
import ArtistCard from "../spotify/ArtistCard";
import TrackRow from "../spotify/TrackRow";
import PlaylistCard from "../spotify/PlaylistCard";
import RecentlyPlayedItem from "../spotify/RecentlyPlayedItem";
import EmptyState from "../shared/EmptyState";
import type {
  SpotifyArtist,
  SpotifyTrack,
  SpotifyPlaylist,
  SpotifyRecentlyPlayedItem,
} from "../../../api/spotify";
import styles from "./SpotifyDataSection.module.css";

type Tab = "artists" | "tracks" | "playlists" | "recent";
type TimeRange = "short_term" | "medium_term" | "long_term";

interface SpotifyDataSectionProps {
  topArtists: SpotifyArtist[];
  topTracks: SpotifyTrack[];
  playlists: SpotifyPlaylist[];
  recentlyPlayed: SpotifyRecentlyPlayedItem[];
  timeRange: TimeRange;
  onTimeRangeChange: (tr: TimeRange) => void;
}

export default function SpotifyDataSection({
  topArtists,
  topTracks,
  playlists,
  recentlyPlayed,
  timeRange,
  onTimeRangeChange,
}: SpotifyDataSectionProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = React.useState<Tab>("artists");

  const TIME_RANGE_LABELS: Record<string, string> = {
    short_term: t("user.spotify.past_month"),
    medium_term: t("user.spotify.past_6_months"),
    long_term: t("user.spotify.all_time"),
  };

  const TABS: { id: Tab; label: string; icon: string }[] = [
    { id: "artists", label: t("user.spotify.top_artists"), icon: "🎤" },
    { id: "tracks", label: t("user.spotify.top_tracks"), icon: "🎵" },
    { id: "playlists", label: t("user.spotify.playlists"), icon: "📋" },
    { id: "recent", label: t("user.spotify.recently_played"), icon: "🕐" },
  ];

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

      {(activeTab === "artists" || activeTab === "tracks") && (
        <div className={styles.timeRangeRow}>
          {(["short_term", "medium_term", "long_term"] as const).map(
            (tr) => (
              <button
                key={tr}
                onClick={() => onTimeRangeChange(tr)}
                className={
                  timeRange === tr
                    ? styles.timeRangeBtnActive
                    : styles.timeRangeBtnInactive
                }
              >
                {TIME_RANGE_LABELS[tr]}
              </button>
            ),
          )}
        </div>
      )}

      <div className={styles.content}>
        {activeTab === "artists" && (
          <div className={styles.artistGrid}>
            {topArtists.length === 0 ? (
              <EmptyState>{t("user.spotify.no_artists")}</EmptyState>
            ) : (
              topArtists.map((a) => (
                <ArtistCard key={a.id} artist={a} />
              ))
            )}
          </div>
        )}

        {activeTab === "tracks" && (
          <div>
            {topTracks.length === 0 ? (
              <EmptyState>{t("user.spotify.no_tracks")}</EmptyState>
            ) : (
              topTracks.map((t, i) => (
                <TrackRow key={t.id} track={t} rank={i + 1} />
              ))
            )}
          </div>
        )}

        {activeTab === "playlists" && (
          <div className={styles.playlistList}>
            {playlists.length === 0 ? (
              <EmptyState>{t("user.spotify.no_playlists")}</EmptyState>
            ) : (
              playlists.map((pl) => (
                <PlaylistCard key={pl.id} playlist={pl} />
              ))
            )}
          </div>
        )}

        {activeTab === "recent" && (
          <div>
            {recentlyPlayed.length === 0 ? (
              <EmptyState>{t("user.spotify.no_recent")}</EmptyState>
            ) : (
              recentlyPlayed.map((item, i) => (
                <RecentlyPlayedItem
                  key={`${item.track.id}-${item.played_at}-${i}`}
                  item={item}
                />
              ))
            )}
          </div>
        )}
      </div>
    </>
  );
}
