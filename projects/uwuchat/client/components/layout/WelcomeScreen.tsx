import { useState } from "react";
import { useTranslation } from "react-i18next";
import LucideIcon from "@/components/shared/LucideIcon";
import styles from "./WelcomeScreen.module.css";

interface Props { onOpenChat: () => void; onOpenCanvas: () => void; onOpenCivitai: () => void; }

export default function WelcomeScreen({ onOpenChat, onOpenCanvas, onOpenCivitai }: Props) {
  const { t } = useTranslation();
  return (
    <div className={styles.wrap}>
      <div className={styles.title}>{t("welcome.title")}</div>
      <div className={styles.subtitle}>{t("welcome.subtitle")}</div>
      <div className={styles.cards}>
        <button onClick={onOpenChat} className={styles.card}>
          <span className={styles.cardIcon}>💬</span>
          <span className={styles.cardLabel}>{t("welcome.chat")}</span>
          <span className={styles.cardDesc}>{t("welcome.chat_desc")}</span>
        </button>
        <button onClick={onOpenCanvas} className={styles.card}>
          <span className={styles.cardIcon}>🎨</span>
          <span className={styles.cardLabel}>{t("welcome.canvas")}</span>
          <span className={styles.cardDesc}>{t("welcome.canvas_desc")}</span>
        </button>
        <button onClick={onOpenCivitai} className={styles.card}>
          <span className={styles.cardIcon}>🖼️</span>
          <span className={styles.cardLabel}>{t("welcome.civitai")}</span>
          <span className={styles.cardDesc}>{t("welcome.civitai_desc")}</span>
        </button>
      </div>
    </div>
  );
}
