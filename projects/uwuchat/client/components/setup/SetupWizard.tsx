import { useState } from "react";
import { useTranslation } from "react-i18next";
import { LanguageStep } from "./LanguageStep";
import { LocationStep } from "./LocationStep";
import { NameStep } from "./NameStep";
import { GenderStep } from "./GenderStep";
import { AvatarStep } from "./AvatarStep";
import { BannerStep } from "./BannerStep";
import { StatusStep } from "./StatusStep";
import { KaomojiStep } from "./KaomojiStep";
import { VerifyEmailStep } from "./VerifyEmailStep";
import { UwuLogo } from "../auth/UwuLogo";
import type { UserProfile } from "../../api/user";
import type { Step } from "./stepTypes";
import { STEPS, initialStep } from "./stepTypes";
import styles from "./SetupWizard.module.css";

interface Props {
  user: UserProfile | null; subscribed: boolean;
  onSave: (values: Partial<UserProfile>) => Promise<boolean>;
  onComplete: () => Promise<void>; onSubscribe: (tier: string) => Promise<void>;
  onDeclinePricing: () => Promise<void>;
}

export function SetupWizard({ user, subscribed, onSave, onComplete, onSubscribe, onDeclinePricing }: Props) {
  const { t } = useTranslation();
  const [step, setStep] = useState<Step>(() => initialStep(user, subscribed));
  const [lang, setLang] = useState("en");
  const [completeError, setCompleteError] = useState(false);
  const visibleSteps = STEPS.filter((s) => s !== "subscribe");
  const currentIdx = visibleSteps.indexOf(step);
  const STEP_TITLES: Record<Step, string> = {
      name: t("setup.step_titles.name"), gender: t("setup.step_titles.gender"),
      language: t("setup.step_titles.language"), location: t("setup.step_titles.location"),
    avatar: t("setup.step_titles.avatar"), banner: t("setup.step_titles.banner"),
    status: t("setup.step_titles.status"), kaomoji: t("setup.step_titles.kaomoji"),
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
        {step === "gender" && <GenderStep onSave={async (gender) => { const ok = await onSave({ gender }); if (ok) advance(); }} onSkip={advance} />}
        {step === "language" && <LanguageStep value={lang} onChange={setLang} onNext={async () => { const ok = await onSave({ preferred_language: lang }); if (ok) advance(); }} />}
        {step === "location" && <LocationStep onSave={async (lat, lon, displayName) => { const ok = await onSave({ latitude: lat, longitude: lon, location_display_name: displayName }); if (ok) advance(); }} onSkip={advance} />}
        {step === "avatar" && <AvatarStep onSkip={advance} />}
        {step === "banner" && <BannerStep onSkip={advance} />}
        {step === "status" && <StatusStep onSave={async (s) => { const d = (user?.data ?? {}) as Record<string, unknown>; const ok = await onSave({ data: { ...d, status_message: s } }); if (ok) advance(); return ok; }} onSkip={advance} />}
        {step === "kaomoji" && <KaomojiStep onSave={async (k) => { const d = (user?.data ?? {}) as Record<string, unknown>; const ok = await onSave({ data: { ...d, kaomoji: k } }); if (ok) advance(); return ok; }} onSkip={advance} />}
        {step === "verify-email" && <VerifyEmailStep onDone={advance} />}
      </div>
    </div>
  );
}
