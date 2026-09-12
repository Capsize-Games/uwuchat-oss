import { useState } from "react";
import { getAvatarSrc } from "../../../utils/avatar";
import styles from "./MessageAvatar.module.css";

export default function MessageAvatar({ isUser, label, emoji, avatarImage, onClick, kaomoji, kaomojiTitle }: {
  isUser: boolean; label: string; emoji?: string; avatarImage?: string | null;
  onClick?: () => void; kaomoji?: string; kaomojiTitle?: string;
}) {
  const [imgFailed, setImgFailed] = useState(false);
  const src = getAvatarSrc(avatarImage);
  const showImg = isUser && src && !imgFailed;

  return (
    <div className="d-flex align-items-center gap-2 mb-1">
      <div onClick={onClick} className={onClick ? styles.avatarClickable : styles.avatarCircle}>
        {showImg ? (
          <img src={src} alt="" className={styles.avatarImg} onError={() => setImgFailed(true)} />
        ) : isUser ? "👤" : emoji || "🤖"}
      </div>
      <small className="fw-bold text-theme-secondary">{label}</small>
      {kaomoji && <span title={kaomojiTitle || undefined} className={styles.kaomoji}>{kaomoji}</span>}
    </div>
  );
}
