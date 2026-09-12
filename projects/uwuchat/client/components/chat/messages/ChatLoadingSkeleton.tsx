import { useTranslation } from "react-i18next";
import styles from "./ChatLoadingSkeleton.module.css";

/**
 * Chat loading indicator — centered spinning ring + label.
 */
export default function ChatLoadingSkeleton() {
  const { t } = useTranslation();

  return (
    <div
      className={styles.outer}
      role="status"
      aria-live="polite"
    >
      <div className={styles.indicatorBadge} aria-hidden="true">
        <span className={styles.indicatorRing} />
      </div>
      <span className={styles.indicatorLabel}>
        {t("chat.loading_conversation")}
      </span>
    </div>
  );
}
