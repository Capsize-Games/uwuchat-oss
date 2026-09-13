import { useTranslation } from "react-i18next";
import LucideIcon from "@/components/shared/LucideIcon";
import styles from "./ImmersionSection.module.css";

interface Props { value: string; onChange: (v: string) => void; }

const OPTIONS = [
  { value: "minimal", icon: "zap", label: "settings.immersion.minimal", desc: "settings.immersion.minimal_desc" },
  { value: "full", icon: "keyboard", label: "settings.immersion.full", desc: "settings.immersion.full_desc" },
];

export default function ImmersionSection({ value, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className={styles.wrap}>
      <p className={styles.desc}>{t("settings.immersion.description")}</p>
      <div className={styles.grid}>
        {OPTIONS.map((opt) => {
          const isActive = value === opt.value;
          return (
            <div key={opt.value} onClick={() => onChange(opt.value)}
              className={isActive ? styles.cardActive : styles.card}>
              {isActive && <span className={styles.cardCheck}>✓</span>}
              <div className={styles.cardIcon}>
                <LucideIcon name={opt.icon} size={28} />
              </div>
              <div className={styles.cardLabel}>{t(opt.label)}</div>
              <div className={styles.cardDesc}>{t(opt.desc)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
