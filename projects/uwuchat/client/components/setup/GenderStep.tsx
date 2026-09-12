import { useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./OptionButton.module.css";

interface Props { onSave: (gender: string) => void; onSkip: () => void; }

export function GenderStep({ onSave, onSkip }: Props) {
  const { t } = useTranslation();
  const [hovered, setHovered] = useState<string | null>(null);

  const OPTIONS = [
    { value: "she/her", label: t("setup.gender.she_her") },
    { value: "he/him", label: t("setup.gender.he_him") },
    { value: "they/them", label: t("setup.gender.they_them") },
    { value: "prefer not to say", label: t("setup.gender.prefer_not") },
  ];

  return (
    <div className={styles.wrap}>
      <p className={styles.desc}>{t("setup.gender.desc")}</p>
      <div className={styles.list}>
        {OPTIONS.map((opt) => (
          <button key={opt.value} onClick={() => onSave(opt.value)}
            onMouseEnter={() => setHovered(opt.value)} onMouseLeave={() => setHovered(null)}
            className={hovered === opt.value ? styles.optBtnHovered : styles.optBtnIdle}>{opt.label}</button>
        ))}
      </div>
      <button onClick={onSkip} className={styles.skipBtn}>{t("setup.gender.skip")}</button>
    </div>
  );
}
