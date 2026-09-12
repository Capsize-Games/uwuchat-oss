import { useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./NameStep.module.css";

interface Props { onSave: (name: string) => void; onSkip: () => void; }

export function NameStep({ onSave, onSkip }: Props) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [focused, setFocused] = useState(false);

  return (
    <div className={styles.wrap}>
      <p className={styles.desc}>{t("setup.name.desc")}</p>
      <input type="text" value={name} onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && name.trim()) onSave(name.trim()); }}
        onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
        placeholder={t("setup.name.placeholder")} maxLength={50} autoFocus
        className={focused ? styles.inputFocused : styles.inputBlurred} />
      <div className={styles.btnRow}>
        <button onClick={() => { if (name.trim()) onSave(name.trim()); }} disabled={!name.trim()}
          className={name.trim() ? styles.continueActive : styles.continueDisabled}>{t("setup.name.continue")}</button>
        <button onClick={onSkip} className={styles.skipBtn}>{t("setup.name.skip")}</button>
      </div>
    </div>
  );
}
