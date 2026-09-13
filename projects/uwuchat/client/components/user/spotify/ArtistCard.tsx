import React from "react";
import type { SpotifyArtist } from "../../../api/spotify";
import styles from "./ArtistCard.module.css";

export default function ArtistCard({
  artist,
}: {
  artist: SpotifyArtist;
}) {
  const image = artist.images[0] ?? null;
  return (
    <div className={styles.card}>
      {image ? (
        <img
          src={image.url}
          alt={artist.name}
          className={styles.artistImg}
          loading="lazy"
        />
      ) : (
        <div className={styles.artistImgFallback}>
          {"\uD83C\uDFB5"}
        </div>
      )}
      <div className={styles.name} title={artist.name}>
        {artist.name}
      </div>
      {artist.genres.length > 0 && (
        <div className={styles.genres}>
          {artist.genres.slice(0, 2).join(", ")}
        </div>
      )}
    </div>
  );
}
