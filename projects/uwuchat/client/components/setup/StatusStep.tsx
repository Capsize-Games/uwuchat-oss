import { useState } from "react";
import { useTranslation } from "react-i18next";
import { WizardButton } from "./WizardButton";
import styles from "./StepShared.module.css";

interface Props { onSave: (status: string) => Promise<boolean>; onSkip: () => void; }

export function StatusStep({ onSave, onSkip }: Props) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  const MAX = 140;

  return (
    <div className={styles.wrap}>
      <p className={`small ${styles.desc}`}>{t("setup.steps.status_desc")}</p>
      <input type="text" value={value} maxLength={MAX} onChange={(e) => setValue(e.target.value)}
        placeholder={t("setup.steps.status_placeholder")} className={styles.statusInput} />
      <div className={styles.statusFooter}>
        <span className={styles.charCount}>{value.length}/{MAX}</span>
        <div className={styles.btnRow}>
          <WizardButton variant="primary" size="sm" disabled={!value.trim()}
            onClick={async () => { if (!value.trim()) return; await onSave(value.trim()); }}>{t("setup.steps.save")}</WizardButton>
          <WizardButton variant="secondary" size="sm" onClick={onSkip}>{t("setup.steps.skip")}</WizardButton>
        </div>
      </div>
    </div>
  );
}
