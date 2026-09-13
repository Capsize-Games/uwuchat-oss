import React from "react";
import type { SpotifyPlaylist } from "../../../api/spotify";
import styles from "./PlaylistCard.module.css";

export default function PlaylistCard({
  playlist,
}: {
  playlist: SpotifyPlaylist;
}) {
  const image = playlist.images[0] ?? null;
  return (
    <a
      href={playlist.spotify_url}
      target="_blank"
      rel="noopener noreferrer"
      className={styles.card}
    >
      {image ? (
        <img
          src={image.url}
          alt={playlist.name}
          className={styles.coverImg}
          loading="lazy"
        />
      ) : (
        <div className={styles.coverFallback}>
          {"\uD83C\uDFB5"}
        </div>
      )}
      <div className={styles.info}>
        <div className={styles.name}>
          {playlist.name}
        </div>
        <div className={styles.trackCount}>
          {playlist.tracks_count} tracks
        </div>
      </div>
      {!playlist.is_public && (
        <span className={styles.lockIcon}>{"\uD83D\uDD12"}</span>
      )}
    </a>
  );
}
