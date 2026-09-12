import React, { useState } from "react";
import ImageUpload from "../ImageUpload";
import type { SpotifyImage } from "../../../api/spotify";
import { getAvatarSrc } from "../../../utils/avatar";
import styles from "./ProfileAvatar.module.css";

interface ProfileAvatarProps {
  displayName: string;
  isOwnProfile: boolean;
  avatarImage: string | null;
  spotifyImage: SpotifyImage | null;
  onAvatarUploaded: (b64: string) => void;
}

export default function ProfileAvatar({
  displayName,
  isOwnProfile,
  avatarImage,
  spotifyImage,
  onAvatarUploaded,
}: ProfileAvatarProps) {
  const border = "3px solid rgba(var(--theme-text-rgb), 0.15)";
  const fallbackBg =
    "var(--theme-accent-muted, rgba(255,255,255,0.1))";

  const [imgFailed, setImgFailed] = useState(false);
  const src = getAvatarSrc(avatarImage);
  const showImg = src && !imgFailed;

  const content = showImg ? (
    <img
      src={src}
      alt=""
      className={styles.avatarImg}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{ border }}
      onError={() => setImgFailed(true)}
    />
  ) : spotifyImage ? (
    <img
      src={spotifyImage.url}
      alt=""
      className={styles.avatarImg}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{ border }}
    />
  ) : (
    <div
      className={styles.avatarFallback}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        background: fallbackBg,
        border,
      }}
    >
      {"👤"}
    </div>
  );

  return (
    <div className={styles.wrapper}>
      {isOwnProfile ? (
        <ImageUpload
          imageType="avatar"
          onUploaded={onAvatarUploaded}
        >
          {content}
        </ImageUpload>
      ) : (
        content
      )}
      <div className={styles.spacer} />
    </div>
  );
}
