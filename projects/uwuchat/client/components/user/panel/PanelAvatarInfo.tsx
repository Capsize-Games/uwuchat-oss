import React from "react";
import { useTranslation } from "react-i18next";
import ImageUpload from "../ImageUpload";
import type { SpotifyImage } from "../../../api/spotify";
import { getAvatarSrc } from "../../../utils/avatar";
import styles from "./PanelAvatarInfo.module.css";

interface PanelAvatarInfoProps {
  displayName: string;
  avatarImage: string | null;
  spotifyImage?: SpotifyImage | null;
  statusMessage: string;
  saving: boolean;
  isEnlarged: boolean;
  onAvatarUploaded: (b64: string) => void;
  onSaveStatus: (status: string) => void;
  kaomojiContent?: React.ReactNode;
}

/**
 * PanelAvatarInfo — avatar circle, display name, kaomoji/badge row,
 * and editable status message, stacked and centered under the
 * banner. Sizes scale down at narrower panel widths.
 */
export default function PanelAvatarInfo({
  displayName,
  avatarImage,
  spotifyImage,
  statusMessage,
  saving,
  isEnlarged,
  onAvatarUploaded,
  onSaveStatus,
  kaomojiContent,
}: PanelAvatarInfoProps) {
  const { t } = useTranslation();
  const [editingStatus, setEditingStatus] = React.useState(false);
  const [statusDraft, setStatusDraft] = React.useState("");
  const [imgFailed, setImgFailed] = React.useState(false);

  const handleSaveStatus = async () => {
    const trimmed = statusDraft.slice(0, 144);
    onSaveStatus(trimmed);
    setEditingStatus(false);
  };

  const src = getAvatarSrc(avatarImage);
  const showImg = src && !imgFailed;

  const avatarContent = showImg ? (
    <img
      src={src}
      alt=""
      className={styles.avatarImg}
      onError={() => setImgFailed(true)}
    />
  ) : spotifyImage ? (
    <img
      src={spotifyImage.url}
      alt=""
      className={styles.avatarImg}
    />
  ) : null;

  const statusDisplay = (
    <div
      className={`${styles.statusDisplay} ${statusMessage ? "" : styles.statusDraftSmall}`}
      onClick={() => {
        setStatusDraft(statusMessage);
        setEditingStatus(true);
      }}
      title={t("user.profile_panel.click_to_set_status")}
    >
      {statusMessage || t("user.profile_panel.what_on_mind")}
    </div>
  );

  return (
    <div className={`${styles.wrapper} ${isEnlarged ? styles.enlarged : ""}`}>
      <ImageUpload imageType="avatar" onUploaded={onAvatarUploaded}>
        {avatarContent || (
          <div className={styles.avatarFallback}>{"👤"}</div>
        )}
      </ImageUpload>
      <span className={styles.displayName}>
        {displayName}
      </span>
      {kaomojiContent && (
        <div className={styles.kaomojiRow}>{kaomojiContent}</div>
      )}
      <div className={styles.statusWrap}>
        {editingStatus ? (
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
            {isEnlarged && (
              <span className={styles.charCount}>
                {statusDraft.length}/144
              </span>
            )}
          </div>
        ) : (
          statusDisplay
        )}
      </div>
    </div>
  );
}
