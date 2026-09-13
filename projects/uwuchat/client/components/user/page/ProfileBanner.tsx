import React from "react";
import ImageUpload from "../ImageUpload";
import styles from "./ProfileBanner.module.css";

interface ProfileBannerProps {
  bannerImage: string | null;
  isOwnProfile: boolean;
  onBannerUploaded: (b64: string) => void;
}

export default function ProfileBanner({
  bannerImage,
  isOwnProfile,
  onBannerUploaded,
}: ProfileBannerProps) {
  return (
    <div
      className={styles.wrap}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        background: bannerImage
          ? undefined
          : "var(--theme-accent-muted, rgba(255,255,255,0.05))",
      }}
    >
      {isOwnProfile ? (
        <ImageUpload
          imageType="banner"
          onUploaded={onBannerUploaded}
          // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
          style={{ width: "100%", height: "100%" }}
        >
          {bannerImage ? (
            <img
              src={`data:image/png;base64,${bannerImage}`}
              alt="banner"
              className={styles.bannerImg}
            />
          ) : (
            <div className={styles.placeholder}>
              Click to add banner
            </div>
          )}
        </ImageUpload>
      ) : bannerImage ? (
        <img
          src={`data:image/png;base64,${bannerImage}`}
          alt="banner"
          className={styles.bannerImg}
        />
      ) : null}
    </div>
  );
}
