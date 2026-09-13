import React from "react";
import type { SpotifyTrack } from "../../../api/spotify";
import styles from "./TrackRow.module.css";

/**
 * TrackRow — a single track row with rank, album art, name, artists, and
 * preview button.
 */
export default function TrackRow({
  track,
  rank,
}: {
  track: SpotifyTrack;
  rank: number;
}) {
  const albumImage = track.album_images[0] ?? null;
  return (
    <div className={styles.row}>
      <span className={styles.rank}>
        {rank}
      </span>
      {albumImage ? (
        <img
          src={albumImage.url}
          alt={track.album_name}
          className={styles.albumArt}
          loading="lazy"
        />
      ) : (
        <div className={styles.albumArtFallback}>
          {"\u266B"}
        </div>
      )}
      <div className={styles.info}>
        <div className={styles.trackName}>
          {track.name}
        </div>
        <div className={styles.artistNames}>
          {track.artists.map((a) => a.name).join(", ")}
        </div>
      </div>
      {track.preview_url && (
        <button
          onClick={() => {
            const audio = new Audio(track.preview_url!);
            audio.volume = 0.5;
            audio.play().catch(() => {});
          }}
          title="Preview"
          className={styles.previewBtn}
        >
          {"\u25B6\uFE0F"}
        </button>
      )}
    </div>
  );
}
