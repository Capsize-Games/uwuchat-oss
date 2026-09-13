import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import ImageUpload from "../ImageUpload";
import GenderBadge from "../GenderBadge";
import { getAvatarSrc } from "../../../utils/avatar";
import styles from "./PanelMobileHeader.module.css";

interface PanelMobileHeaderProps {
  displayName: string;
  avatarImage: string | null;
  bannerImage: string | null;
  bannerFallback: string;
  statusMessage: string;
  gender: string | null;
  saving: boolean;
  onAvatarUploaded: (b64: string) => void;
  onBannerUploaded: (b64: string) => void;
  onSaveStatus: (status: string) => void;
  kaomojiContent?: React.ReactNode;
}

const HEADER_HEIGHT = 68;
const AVATAR_SIZE = 40;

/**
 * PanelMobileHeader — mobile-only profile header. Folds the avatar,
 * name, status, and badges directly into the banner strip as a single
 * row instead of the desktop design's centered block stacked below
 * the banner, so the header only costs the banner's own height.
 */
export default function PanelMobileHeader({
  displayName,
  avatarImage,
  bannerImage,
  bannerFallback,
  statusMessage,
  gender,
  saving,
  onAvatarUploaded,
  onBannerUploaded,
  onSaveStatus,
  kaomojiContent,
}: PanelMobileHeaderProps) {
  const { t } = useTranslation();
  const [editingStatus, setEditingStatus] = useState(false);
  const [statusDraft, setStatusDraft] = useState("");

  const handleSaveStatus = () => {
    onSaveStatus(statusDraft.slice(0, 144));
    setEditingStatus(false);
  };

  const avatarSrc = getAvatarSrc(avatarImage);
  const statusClass = statusMessage
    ? styles.statusText
    : styles.statusTextPlaceholder;

  return (
    <div>
      <div
        className={styles.bannerWrap}
        // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
        style={{
          height: HEADER_HEIGHT,
          background: bannerImage ? undefined : bannerFallback,
        }}
      >
        <ImageUpload
          imageType="banner"
          onUploaded={onBannerUploaded}
          // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
          style={{ width: "100%", height: "100%" }}
        >
          {bannerImage && (
            <img
              src={`data:image/png;base64,${bannerImage}`}
              alt="banner"
              className={styles.bannerImg}
            />
          )}
        </ImageUpload>

        {/* Row overlay — avatar, name/status, badges */}
        <div className={styles.overlay}>
          <ImageUpload imageType="avatar" onUploaded={onAvatarUploaded}>
            {avatarSrc ? (
              <img
                src={avatarSrc}
                alt=""
                className={styles.avatarImg}
                // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                style={{
                  width: AVATAR_SIZE,
                  height: AVATAR_SIZE,
                }}
              />
            ) : (
              <div
                className={styles.avatarFallback}
                // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                style={{
                  width: AVATAR_SIZE,
                  height: AVATAR_SIZE,
                }}
              >
                {"👤"}
              </div>
            )}
          </ImageUpload>

          <div className={styles.infoCol}>
            <div className={styles.displayName}>
              {displayName}
            </div>
            <div
              onClick={() => {
                setStatusDraft(statusMessage);
                setEditingStatus(true);
              }}
              className={statusClass}
            >
              {statusMessage || t("user.profile_panel.what_on_mind")}
            </div>
          </div>

          {kaomojiContent && (
            <div className={styles.kaomojiWrap}>
              {kaomojiContent}
            </div>
          )}
          <GenderBadge gender={gender} />
        </div>
      </div>

      {editingStatus && (
        <div className={styles.editorRow}>
          <input
            type="text"
            value={statusDraft}
            onChange={(e) => setStatusDraft(e.target.value)}
            maxLength={144}
            autoFocus
            placeholder={t("user.profile_panel.status_placeholder")}
            className={styles.editorInput}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSaveStatus();
              if (e.key === "Escape") setEditingStatus(false);
            }}
          />
          <button
            onClick={handleSaveStatus}
            disabled={saving}
            className={styles.editorSave}
          >
            {saving ? "..." : t("common.save")}
          </button>
          <button
            onClick={() => setEditingStatus(false)}
            className={styles.editorCancel}
          >
            {"✕"}
          </button>
        </div>
      )}
    </div>
  );
}
