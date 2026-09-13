import { useState, useEffect } from "react";
import { ArrowLeft, Mail, UserStar } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { PublicShell } from "../layout/PublicShell";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import pageStyles from "./AuthShared.module.css";

const GOOGLE_OAUTH_URL = "/api/v1/auth/oauth/google/login";
const STEAM_AUTH_API = "/api/v1/steam/auth/login?mode=auth";
const CAPABILITIES_URL = "/api/v1/auth/oauth/capabilities";

export default function RegisterPage() {
  const { t } = useTranslation(); const navigate = useNavigate();
  const spa = (path: string) => (e: React.MouseEvent) => { e.preventDefault(); navigate(path); };
  const { register, isLoggingIn } = useAuth();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState(""); const [inviteCode, setInviteCode] = useState("");
  const [ageConfirmed, setAgeConfirmed] = useState(false); const [tosAgreed, setTosAgreed] = useState(false);
  const [entertainmentConfirmed, setEntertainmentConfirmed] = useState(false);
  const [sensitiveDataConsent, setSensitiveDataConsent] = useState(false);
  const [error, setError] = useState<string | null>(null); const [inviteRequired, setInviteRequired] = useState<boolean | null>(null);
  const [steamLoading, setSteamLoading] = useState(false);
  const [googleConfigured, setGoogleConfigured] = useState(false);
  useEffect(() => { let c = false; fetch(CAPABILITIES_URL).then(r => r.json()).then((d: { google?: boolean }) => { if (!c) setGoogleConfigured(!!d.google); }).catch(() => {}); return () => { c = true; }; }, []);
  const [agreed, setAgreed] = useState(false); const [showEmailForm, setShowEmailForm] = useState(false);
  useEffect(() => { let c = false; fetch("/api/v1/auth/invite-required").then(r => r.json()).then((d: { required: boolean }) => { if (!c) setInviteRequired(d.required); }).catch(() => { if (!c) setInviteRequired(false); }); return () => { c = true; }; }, []);
  const allChecked = ageConfirmed && tosAgreed && entertainmentConfirmed;
  const canSubmit = !isLoggingIn && allChecked && email.trim() !== "" && password.trim() !== "" && confirmPassword.trim() !== "" && password === confirmPassword;
  const handleSubmit = async (e: React.FormEvent) => { e.preventDefault(); setError(null); if (password !== confirmPassword) { setError(t("auth.register.error_passwords_match")); return; } if (password.length < 8) { setError(t("auth.register.error_password_length")); return; } try { await register(email, password, { tos_agreed: tosAgreed, age_confirmed: ageConfirmed, entertainment_confirmed: entertainmentConfirmed, sensitive_data_consent_agreed: sensitiveDataConsent }, inviteCode); navigate("/"); } catch (err) { setError(err instanceof Error ? err.message : t("auth.register.error_failed")); } };

  const titleH1 = <h1 className={`auth-title ${pageStyles.titleH1}`}><UserStar size={22} />{t("auth.register.title")}</h1>;

  if (inviteRequired === null) return <PublicShell><div className={`auth-page ${pageStyles.page}`}><div className={`auth-card ${pageStyles.card}`}><div className={pageStyles.titleRow}>{titleH1}</div><div className="d-flex justify-content-center py-4"><LoadingSpinner /></div></div></div></PublicShell>;

  return (
    <PublicShell>
    <div className={`auth-page ${pageStyles.page}`}>
    <div className={`auth-card ${pageStyles.card}`}>
      <div className={pageStyles.titleRow}>
        {agreed && showEmailForm && <button type="button" onClick={() => { setShowEmailForm(false); setError(null); }} aria-label={t("auth.register.back")} className={pageStyles.backBtn}><ArrowLeft size={18} /></button>}
        {titleH1}
      </div>
      {!agreed && <div><div className="auth-agreements"><div className="form-check"><input className="form-check-input" type="checkbox" id="age-confirm" checked={ageConfirmed} onChange={(e) => setAgeConfirmed(e.target.checked)} /><label className="form-check-label" htmlFor="age-confirm">{t("auth.register.age_confirm")}</label></div><div className="form-check"><input className="form-check-input" type="checkbox" id="tos-agree" checked={tosAgreed} onChange={(e) => setTosAgreed(e.target.checked)} /><label className="form-check-label" htmlFor="tos-agree">{t("auth.register.tos_agree_before")} <a href="/terms" className="auth-link" onClick={spa("/terms")}>{t("auth.register.terms_of_service")}</a> {t("auth.register.tos_agree_and")} <a href="/privacy" className="auth-link" onClick={spa("/privacy")}>{t("auth.register.privacy_policy")}</a>.</label></div><div className="form-check"><input className="form-check-input" type="checkbox" id="entertainment-confirm" checked={entertainmentConfirmed} onChange={(e) => setEntertainmentConfirmed(e.target.checked)} /><label className="form-check-label" htmlFor="entertainment-confirm">{t("auth.register.entertainment_confirm")}</label></div><div className="form-check"><input className="form-check-input" type="checkbox" id="sensitive-data-consent" checked={sensitiveDataConsent} onChange={(e) => setSensitiveDataConsent(e.target.checked)} /><label className="form-check-label" htmlFor="sensitive-data-consent">{t("auth.register.sensitive_data_consent")}</label></div></div><button type="button" className="btn btn-primary w-100 mt-3" disabled={!allChecked} onClick={() => setAgreed(true)}>Next</button></div>}
      {agreed && !showEmailForm && <div><button type="button" className="btn auth-provider-btn w-100 mb-3" onClick={() => setShowEmailForm(true)} disabled={!allChecked}><span className="auth-provider-btn-content"><Mail size={18} /><span className="auth-provider-btn-label">{t("auth.register.sign_up_email")}</span></span></button>{googleConfigured && <button type="button" className="btn auth-provider-btn w-100 mb-3" onClick={() => { window.location.href = GOOGLE_OAUTH_URL; }} disabled={!allChecked}><GoogleIcon /><span className="auth-provider-btn-label">{t("auth.register.sign_up_google")}</span></button>}<button type="button" className="btn auth-provider-btn w-100 mb-3" onClick={async () => { setSteamLoading(true); try { const res = await fetch(STEAM_AUTH_API); if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error((err as { detail?: string }).detail || "Steam sign-in failed"); } const data = await res.json() as { url: string }; window.location.href = data.url; } catch (err) { console.error("Steam sign-up failed:", err); setSteamLoading(false); } }} disabled={!allChecked || steamLoading}><SteamIcon /><span className="auth-provider-btn-label">{steamLoading ? t("auth.login.steam_connecting") : t("auth.register.sign_up_steam")}</span></button></div>}
      {agreed && showEmailForm && <div><form onSubmit={handleSubmit}><div className="mb-3"><label className="form-label text-secondary small">{t("auth.register.email_label")}</label><input type="email" className="form-control auth-input" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" /></div><div className="mb-3"><label className="form-label text-secondary small">{t("auth.register.password_label")}</label><input type="password" className="form-control auth-input" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} autoComplete="new-password" /></div><div className="mb-3"><label className="form-label text-secondary small">{t("auth.register.confirm_password_label")}</label><input type="password" className="form-control auth-input" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required minLength={8} autoComplete="new-password" /></div>{inviteRequired && <div className="mb-3"><label className="form-label text-secondary small">{t("auth.register.invite_code_label")}</label><input type="text" className="form-control auth-input" value={inviteCode} onChange={(e) => setInviteCode(e.target.value)} placeholder={t("auth.register.invite_code_placeholder")} autoComplete="off" /></div>}{error && <div className="alert alert-danger py-2 mb-3 mt-3" role="alert">{error}</div>}<button type="submit" className="btn btn-primary w-100 mb-3 mt-3" disabled={!canSubmit}>{isLoggingIn ? t("auth.register.creating") : t("auth.register.submit")}</button></form></div>}
      <p className="text-center text-secondary small mb-0">{t("auth.register.already_have_account")} <a href="/login" className="auth-link" onClick={(e) => { e.preventDefault(); navigate("/login"); }}>{t("auth.register.sign_in")}</a></p>
    </div></div></PublicShell>
  );
}

function GoogleIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="currentColor"><path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/></svg>; }
function SteamIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="currentColor"><path d="M11.979 0C5.678 0 .511 4.86.022 11.037l6.432 2.658c.545-.371 1.203-.59 1.912-.59.063 0 .125.004.188.006l2.861-4.142V8.91c0-2.495 2.028-4.524 4.524-4.524 2.494 0 4.524 2.031 4.524 4.527s-2.03 4.525-4.524 4.525h-.105l-4.076 2.911c0 .052.004.105.004.159 0 1.875-1.515 3.396-3.39 3.396-1.635 0-3.016-1.173-3.331-2.727L.436 15.27C1.862 20.307 6.486 24 11.979 24c6.627 0 11.999-5.373 11.999-12S18.605 0 11.979 0zM7.54 18.21l-1.473-.61c.262.543.714.999 1.314 1.25 1.297.539 2.793-.076 3.332-1.375.263-.63.264-1.319.005-1.949s-.75-1.121-1.377-1.383c-.624-.26-1.29-.249-1.878-.03l1.523.63c.956.4 1.409 1.5 1.009 2.455-.397.957-1.497 1.41-2.454 1.012H7.54zm11.415-9.303c0-1.662-1.353-3.015-3.015-3.015-1.665 0-3.015 1.353-3.015 3.015 0 1.665 1.35 3.015 3.015 3.015 1.663 0 3.015-1.35 3.015-3.015zm-5.273-.005c0-1.252 1.013-2.266 2.265-2.266 1.249 0 2.266 1.014 2.266 2.266 0 1.251-1.017 2.265-2.266 2.265-1.253 0-2.265-1.014-2.265-2.265z"/></svg>; }
