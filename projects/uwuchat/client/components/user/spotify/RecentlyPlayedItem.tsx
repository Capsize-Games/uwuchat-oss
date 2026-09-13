import React from "react";
import type { SpotifyRecentlyPlayedItem } from "../../../api/spotify";
import { getTimeAgo } from "../../../utils/time";
import styles from "./RecentlyPlayedItem.module.css";

export default function RecentlyPlayedItem({
  item,
}: {
  item: SpotifyRecentlyPlayedItem;
}) {
  const albumImage = item.track.album_images[0] ?? null;
  const playedDate = new Date(item.played_at);
  const timeAgo = getTimeAgo(playedDate);

  return (
    <div className={styles.row}>
      {albumImage ? (
        <img
          src={albumImage.url}
          alt={item.track.album_name}
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
          {item.track.name}
        </div>
        <div className={styles.artistNames}>
          {item.track.artists.map((a) => a.name).join(", ")}
        </div>
      </div>
      <span className={styles.timeAgo}>
        {timeAgo}
      </span>
    </div>
  );
}
