import { useTranslation } from "react-i18next";
import styles from "./UwuReadyNotification.module.css";
import type { UwuReadyChatbot } from "../../hooks/useUwuCreation";

interface Props {
  chatbot: UwuReadyChatbot;
  onDismiss: () => void;
}

/** One-time "your new UwU is ready" notice — shown once per creation. */
export default function UwuReadyNotification({ chatbot, onDismiss }: Props) {
  const { t } = useTranslation();
  return (
    <div className={styles.backdrop} onClick={onDismiss}>
      <div
        className={styles.modal}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={t("sidebar.uwu_ready_title")}
      >
        <div className={styles.emoji}>✨</div>
        <h2 className={styles.title}>{t("sidebar.uwu_ready_title")}</h2>
        <p className={styles.body}>
          {t("sidebar.uwu_ready_body", { name: chatbot.name })}
        </p>
        <button type="button" className={styles.cta} onClick={onDismiss}>
          {t("sidebar.uwu_ready_cta")}
        </button>
      </div>
    </div>
  );
}
