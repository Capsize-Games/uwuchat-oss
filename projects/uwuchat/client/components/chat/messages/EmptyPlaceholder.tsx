import { useTranslation } from "react-i18next";
import styles from "./EmptyPlaceholder.module.css";

interface EmptyPlaceholderProps {
  emoji?: string; greeting?: string; onSelectOpener?: (text: string) => void;
  botName?: string; onProfileClick?: () => void;
}

export default function EmptyPlaceholder({ emoji, greeting, onSelectOpener, botName, onProfileClick }: EmptyPlaceholderProps) {
  const { t } = useTranslation();
  const displayText = greeting || t("chat.empty_placeholder.greeting_fallback");
  const openers = [t("chat.empty_placeholder.opener_how_are_you"), t("chat.empty_placeholder.opener_what_can_you_do")];

  return (
    <div className={`d-flex align-items-center justify-content-center ${styles.outer}`}>
      <div className={`d-flex flex-column align-items-center ${styles.card}`}>
        <div className={emoji ? styles.emojiLarge : styles.emojiDefault}>{emoji ?? "✨"}</div>
        <p className={styles.greeting}>{displayText}</p>
        {botName && onProfileClick && (
          <button type="button" onClick={onProfileClick} className={styles.profileBtn}>{t("chat.view_profile")}</button>
        )}
        {onSelectOpener && (
          <div className={`d-flex flex-wrap justify-content-center ${styles.chipRow}`}>
            {openers.map((text) => (
              <button key={text} type="button" onClick={() => onSelectOpener(text)} className={styles.chip}>{text}</button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
