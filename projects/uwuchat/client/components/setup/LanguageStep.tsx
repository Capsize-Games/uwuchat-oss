import { useTranslation } from "react-i18next";
import { LANGUAGES } from "./LANGUAGES";
import styles from "./LanguageStep.module.css";

interface Props { value: string; onChange: (code: string) => void; onNext: () => void; }

export function LanguageStep({ value, onChange, onNext }: Props) {
  const { t } = useTranslation();
  return (
    <div className={styles.wrap}>
      <p className={styles.desc}>{t("setup.language.description")}</p>
      <div className={styles.grid}>
        {LANGUAGES.map((lang) => (
          <button key={lang.code} onClick={() => onChange(lang.code)}
            className={value === lang.code ? styles.langBtnSelected : styles.langBtnUnselected}>
            <div className={styles.langNative}>{lang.native}</div>
            <div className={styles.langLabel}>{lang.label}</div>
          </button>
        ))}
      </div>
      <button onClick={onNext} className={styles.continueBtn}>{t("setup.language.continue")}</button>
    </div>
  );
}
