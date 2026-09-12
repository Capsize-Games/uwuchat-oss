import { useState } from "react";
import { useTranslation } from "react-i18next";
import { LanguageStep } from "./LanguageStep";
import { NameStep } from "./NameStep";
import { VerifyEmailStep } from "./VerifyEmailStep";
import { UwuLogo } from "../auth/UwuLogo";
import type { UserProfile } from "../../api/user";
import type { Step } from "./stepTypes";
import { STEPS, initialStep } from "./stepTypes";
import styles from "./SetupWizard.module.css";

interface Props {
  user: UserProfile | null;
  onSave: (values: Partial<UserProfile>) => Promise<boolean>;
  onComplete: () => Promise<void>;
}

export function SetupWizard({ user, onSave, onComplete }: Props) {
  const { t } = useTranslation();
  const [step, setStep] = useState<Step>(() => initialStep(user));
  const [lang, setLang] = useState(user?.preferred_language ?? "en");
  const [completeError, setCompleteError] = useState(false);
  const visibleSteps = STEPS;
  const currentIdx = visibleSteps.indexOf(step);
  const STEP_TITLES: Record<Step, string> = {
      name: t("setup.step_titles.name"),
      language: t("setup.step_titles.language"),
    "verify-email": t("setup.step_titles.verify_email"),
  };

  const advance = () => {
    const idx = visibleSteps.indexOf(step);
    if (idx < visibleSteps.length - 1) { setStep(visibleSteps[idx + 1]); return; }
    handleComplete();
  };

  const handleComplete = async () => {
    sessionStorage.removeItem("uwuchat_continue_wizard");
    setCompleteError(false);
    try { await onComplete(); } catch { setCompleteError(true); }
  };

  return (
    <div className={styles.overlay}>
      <div className={styles.card}>
        <div className={styles.logoWrap}><UwuLogo size={22} /></div>
        <div className={styles.stepMeta}>
          <div className={styles.stepHeader}>
            <span className={styles.stepLabel}>{t("setup.wizard.step_of", { step: currentIdx + 1, total: visibleSteps.length })}</span>
            <div className={styles.progressDots}>
              {visibleSteps.map((s, i) => (
                <div key={s} className={i <= currentIdx ? styles.progressDotActive : styles.progressDotInactive} />
              ))}
            </div>
          </div>
          <h2 className={styles.stepTitle}>{STEP_TITLES[step]}</h2>
        </div>

        {completeError && (
          <div className={styles.errorBox}>
            <span>{t("setup.wizard.complete_error", "Something went wrong finishing setup. Please try again.")}</span>
            <button onClick={() => { void handleComplete(); }} className={styles.retryBtn}>{t("setup.wizard.retry", "Retry")}</button>
          </div>
        )}

        {step === "name" && <NameStep onSave={async (name) => { const ok = await onSave({ display_name: name }); if (ok) advance(); }} onSkip={advance} />}
        {step === "language" && <LanguageStep value={lang} onChange={setLang} onNext={async () => { const ok = await onSave({ preferred_language: lang }); if (ok) advance(); }} />}
        {step === "verify-email" && <VerifyEmailStep onDone={advance} />}
      </div>
    </div>
  );
}
