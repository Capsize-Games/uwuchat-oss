import { useState } from "react";
import { useTranslation } from "react-i18next";
import pageStyles from "./TosAgreementPage.module.css";
import { useAuth } from "../../hooks/useAuth";
import { agreeToTerms } from "../../../../../extensions/auth/client/api";

export default function TosAgreementPage() {
  const { t } = useTranslation();
  const { accessToken } = useAuth();
  const [ageConfirmed, setAgeConfirmed] = useState(false);
  const [tosAgreed, setTosAgreed] = useState(false);
  const [entertainmentConfirmed, setEntertainmentConfirmed] = useState(false);
  const [sensitiveDataConsent, setSensitiveDataConsent] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const allChecked = ageConfirmed && tosAgreed && entertainmentConfirmed;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); if (!allChecked || !accessToken) return;
    setError(null); setIsSubmitting(true);
    try { await agreeToTerms({ tos_agreed: true, age_confirmed: true, entertainment_confirmed: true, sensitive_data_consent_agreed: sensitiveDataConsent }, accessToken); window.location.href = "/"; }
    catch (err) { setError(err instanceof Error ? err.message : t("auth.tos.error_failed")); }
    finally { setIsSubmitting(false); }
  };

  return (
    <div className={`auth-page ${pageStyles.page}`}>
      <div className={`auth-card ${pageStyles.card}`}>
        <h1 className={`auth-title ${pageStyles.title}`}>{t("auth.tos.title")}</h1>
        <p className={`text-secondary text-center mb-4 ${pageStyles.subtitle}`}>{t("auth.tos.subtitle")}</p>
        <form onSubmit={handleSubmit}>
          <div className={`auth-agreements ${pageStyles.agreements}`}>
            <div className="form-check"><input className="form-check-input" type="checkbox" id="age-confirm" checked={ageConfirmed} onChange={(e) => setAgeConfirmed(e.target.checked)} /><label className="form-check-label" htmlFor="age-confirm">{t("auth.register.age_confirm")}</label></div>
            <div className="form-check"><input className="form-check-input" type="checkbox" id="tos-agree" checked={tosAgreed} onChange={(e) => setTosAgreed(e.target.checked)} /><label className="form-check-label" htmlFor="tos-agree">{t("auth.register.tos_agree_before")} <a href="/terms" className="auth-link">{t("auth.register.terms_of_service")}</a> {t("auth.register.tos_agree_and")} <a href="/privacy" className="auth-link">{t("auth.register.privacy_policy")}</a>.</label></div>
            <div className="form-check"><input className="form-check-input" type="checkbox" id="entertainment-confirm" checked={entertainmentConfirmed} onChange={(e) => setEntertainmentConfirmed(e.target.checked)} /><label className="form-check-label" htmlFor="entertainment-confirm">{t("auth.register.entertainment_confirm")}</label></div>
            <div className="form-check"><input className="form-check-input" type="checkbox" id="sensitive-data-consent" checked={sensitiveDataConsent} onChange={(e) => setSensitiveDataConsent(e.target.checked)} /><label className="form-check-label" htmlFor="sensitive-data-consent">{t("auth.tos.sensitive_data_consent")}</label></div>
          </div>
          {error && <div className="alert alert-danger py-2 mt-3 mb-0" role="alert">{error}</div>}
          <button type="submit" className="btn btn-primary w-100 mt-4" disabled={!allChecked || isSubmitting}>{isSubmitting ? t("auth.tos.saving") : t("auth.tos.submit")}</button>
        </form>
      </div>
    </div>
  );
}
