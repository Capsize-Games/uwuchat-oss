import { useState } from "react";
import { useTranslation } from "react-i18next";
import KaomojiPicker from "../user/KaomojiPicker";
import { WizardButton } from "./WizardButton";
import styles from "./KaomojiStep.module.css";

interface Props { onSave: (kaomoji: string) => Promise<boolean>; onSkip: () => void; }

export function KaomojiStep({ onSave, onSkip }: Props) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");

  return (
    <div className={styles.wrap}>
      <p className={`small ${styles.desc}`}>{t("setup.steps.kaomoji_desc")}</p>
      <KaomojiPicker value={value} isOwnProfile={true} onSave={async (k) => { setValue(k); await onSave(k); }} />
      <div className={styles.btnRow}>
        <WizardButton variant="secondary" onClick={onSkip}>{t("setup.steps.skip")}</WizardButton>
      </div>
    </div>
  );
}
