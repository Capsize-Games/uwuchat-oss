import React from "react";
import styles from "./SpotifyConnectSection.module.css";

interface SpotifyConnectSectionProps {
  onConnect: () => void;
}

export default function SpotifyConnectSection({
  onConnect,
}: SpotifyConnectSectionProps) {
  return (
    <div className={styles.card}>
      <div className={styles.icon}>{"\uD83C\uDFA7"}</div>
      <div className={styles.desc}>
        Share your music taste on your profile
      </div>
      <button onClick={onConnect} className={styles.connectBtn}>
        Connect Spotify
      </button>
    </div>
  );
}
