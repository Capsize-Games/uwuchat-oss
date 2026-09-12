import React from "react";
import KaomojiPicker from "./KaomojiPicker";
import styles from "./ProfileInfoBar.module.css";

interface ProfileInfoBarProps {
  kaomoji: string;
  isOwnProfile: boolean;
  onSaveKaomoji: (k: string) => void;
  countryCode: string | null;
}

function countryFlag(code: string): string {
  if (code.length !== 2) return "";
  const a = 0x1F1E6 - 65 + code[0].toUpperCase().charCodeAt(0);
  const b = 0x1F1E6 - 65 + code[1].toUpperCase().charCodeAt(0);
  return String.fromCodePoint(a, b);
}

export default function ProfileInfoBar({
  kaomoji,
  isOwnProfile,
  onSaveKaomoji,
  countryCode,
}: ProfileInfoBarProps) {
  const flag = countryCode ? countryFlag(countryCode) : "";
  const hasInfo = !!flag;

  return (
    <div className={styles.row}>
      <KaomojiPicker
        value={kaomoji}
        isOwnProfile={isOwnProfile}
        onSave={onSaveKaomoji}
      />

      {hasInfo && (
        <div className={styles.infoRow}>
          {flag && (
            <span className={styles.flagBadge}>
              {flag}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
