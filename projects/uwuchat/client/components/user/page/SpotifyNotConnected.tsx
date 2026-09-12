import React from "react";
import styles from "./SpotifyNotConnected.module.css";

interface SpotifyNotConnectedProps {
  displayName: string;
  statusMessage?: string;
}

export default function SpotifyNotConnected({
  displayName,
  statusMessage,
}: SpotifyNotConnectedProps) {
  const isImporting =
    statusMessage === "scraping" || statusMessage === "pending";

  if (isImporting) {
    return (
      <div className={styles.wrap}>
        <div className={styles.importing}>
          Spotify data is being imported&hellip;
        </div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.icon}>{"\uD83C\uDFA7"}</div>
        <div className={styles.message}>
          {displayName} hasn't linked their Spotify yet.
        </div>
      </div>
    </div>
  );
}
