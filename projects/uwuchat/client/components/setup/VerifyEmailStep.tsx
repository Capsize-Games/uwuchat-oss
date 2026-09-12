import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { WizardButton } from "./WizardButton";
import styles from "./VerifyEmailStep.module.css";

interface Props { onDone: () => void; }

export function VerifyEmailStep({ onDone }: Props) {
  const { t } = useTranslation();
  const { user, accessToken } = useAuth();
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isVerified = user?.is_verified === true;
  const email = user?.email ?? "";

  const send = async () => {
    if (!accessToken) return;
    setSending(true); setError(null);
    try {
      const res = await fetch("/api/v1/auth/send-verification", { method: "POST", headers: { Authorization: `Bearer ${accessToken}` } });
      if (!res.ok) { const body = await res.json().catch(() => ({})); throw new Error(body.detail || "Failed to send verification email"); }
      setSent(true);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to send verification email"); }
    finally { setSending(false); }
  };

  return (
    <div className={styles.wrap}>
      <p className={`small ${styles.desc}`}>{t("setup.steps.verify_email_desc")}</p>
      {isVerified ? (
        <div className={styles.verifiedBox}>{t("setup.steps.already_verified")}</div>
      ) : sent ? (
        <div className={styles.sentBox}>
          <p className={`small ${styles.sentText}`}>{t("setup.steps.verification_sent", { email })}</p>
          <WizardButton variant="secondary" size="sm" className={styles.resendBtn} onClick={send} disabled={sending}>{t("setup.steps.resend_verification")}</WizardButton>
        </div>
      ) : (
        <div className={styles.pendingWrap}>
          {error && <div className={styles.errorText}>{error}</div>}
          <WizardButton variant="primary" size="lg" onClick={send} disabled={sending}>{sending ? t("setup.steps.sending") : t("setup.steps.send_verification")}</WizardButton>
        </div>
      )}
      <div className={styles.doneRow}>
        <WizardButton variant="primary" size="xl" onClick={onDone}>{t("setup.steps.done")}</WizardButton>
      </div>
    </div>
  );
}
