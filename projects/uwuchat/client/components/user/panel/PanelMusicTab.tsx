import React from "react";
import { useTranslation } from "react-i18next";
import ArtistCard from "../spotify/ArtistCard";
import TrackRow from "../spotify/TrackRow";
import PlaylistCard from "../spotify/PlaylistCard";
import RecentlyPlayedItem from "../spotify/RecentlyPlayedItem";
import EmptyState from "../shared/EmptyState";
import SpotifyConnectSection from "./SpotifyConnectSection";
import type {
  SpotifyArtist,
  SpotifyProfile,
  SpotifyTrack,
} from "../../../api/spotify";
import styles from "./PanelMusicTab.module.css";

interface PanelMusicTabProps {
  spotifyConnected: boolean;
  spotifyLoading: boolean;
  spotifyProfile: SpotifyProfile | null;
  onConnect: () => void;
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className={styles.sectionLabel}>{children}</div>;
}

export default function PanelMusicTab({
  spotifyConnected,
  spotifyLoading,
  spotifyProfile,
  onConnect,
}: PanelMusicTabProps) {
  const { t } = useTranslation();
  const [timeRange, setTimeRange] = React.useState<
    "short_term" | "medium_term" | "long_term"
  >("medium_term");

  const TIME_RANGE_LABELS: Record<string, string> = {
    short_term: t("user.panel_music.past_month"),
    medium_term: t("user.panel_music.past_6_months"),
    long_term: t("user.panel_music.all_time"),
  };

  if (!spotifyConnected && !spotifyLoading) {
    return <SpotifyConnectSection onConnect={onConnect} />;
  }

  if (!spotifyConnected || !spotifyProfile) return null;

  const topArtists: SpotifyArtist[] =
    timeRange === "short_term"
      ? spotifyProfile.top_artists_short ?? []
      : timeRange === "medium_term"
        ? spotifyProfile.top_artists_medium ?? []
        : spotifyProfile.top_artists_long ?? [];

  const topTracks: SpotifyTrack[] =
    timeRange === "short_term"
      ? spotifyProfile.top_tracks_short ?? []
      : timeRange === "medium_term"
        ? spotifyProfile.top_tracks_medium ?? []
        : spotifyProfile.top_tracks_long ?? [];

  const playlists = spotifyProfile.playlists ?? [];
  const recentlyPlayed = spotifyProfile.recently_played ?? [];

  return (
    <>
      <div className={styles.timeRangeRow}>
        {(["short_term", "medium_term", "long_term"] as const).map(
          (tr) => (
            <button
              key={tr}
              onClick={() => setTimeRange(tr)}
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

      <SectionLabel>{t("user.panel_music.top_artists")}</SectionLabel>
      <div className={styles.artistGrid}>
        {topArtists.length === 0 ? (
          <EmptyState>{t("user.panel_music.no_artists")}</EmptyState>
        ) : (
          topArtists.map((a) => (
            <ArtistCard key={a.id} artist={a} />
          ))
        )}
      </div>

      <SectionLabel>{t("user.panel_music.top_tracks")}</SectionLabel>
      <div className={styles.trackList}>
        {topTracks.length === 0 ? (
          <EmptyState>{t("user.panel_music.no_tracks")}</EmptyState>
        ) : (
          topTracks.map((track, i) => (
            <TrackRow key={track.id} track={track} rank={i + 1} />
          ))
        )}
      </div>

      <SectionLabel>{t("user.panel_music.playlists")}</SectionLabel>
      <div className={styles.playlistList}>
        {playlists.length === 0 ? (
          <EmptyState>{t("user.panel_music.no_playlists")}</EmptyState>
        ) : (
          playlists.map((pl) => (
            <PlaylistCard key={pl.id} playlist={pl} />
          ))
        )}
      </div>

      <SectionLabel>{t("user.panel_music.recently_played")}</SectionLabel>
      <div>
        {recentlyPlayed.length === 0 ? (
          <EmptyState>{t("user.panel_music.no_recently_played")}</EmptyState>
        ) : (
          recentlyPlayed.map((item, i) => (
            <RecentlyPlayedItem
              key={`${item.track.id}-${item.played_at}-${i}`}
              item={item}
            />
          ))
        )}
      </div>
    </>
  );
}
