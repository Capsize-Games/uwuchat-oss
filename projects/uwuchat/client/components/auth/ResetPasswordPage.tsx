import { FormEvent, useState } from "react";
import { Lock } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PublicShell } from "../layout/PublicShell";
import { UwuLogo } from "./UwuLogo";
import pageStyles from "./AuthShared.module.css";

const RESET_CONFIRM_URL = "/api/v1/auth/password-reset/confirm";

export default function ResetPasswordPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault(); setError(null);
    if (newPassword !== confirmPassword) { setError(t("auth.password_reset.error_passwords_match")); return; }
    if (newPassword.length < 8) { setError(t("auth.password_reset.error_password_length")); return; }
    if (!token) { setError(t("auth.password_reset.error_missing_token")); return; }
    setLoading(true);
    try {
      const res = await fetch(RESET_CONFIRM_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token, new_password: newPassword }) });
      if (!res.ok) { const body = await res.json().catch(() => ({})); throw new Error((body as { detail?: string }).detail || t("auth.password_reset.confirm_error")); }
      navigate("/login?reset=1");
    } catch (err) { setError(err instanceof Error ? err.message : t("auth.password_reset.confirm_error")); }
    finally { setLoading(false); }
  };

  const header = (
    <div className={pageStyles.titleRow}>
      <Lock size={22} />
      <h1 className={`auth-title ${pageStyles.titleH1}`}>{t("auth.password_reset.confirm_title")}</h1>
    </div>
  );

  if (!token) return <PublicShell><div className={`auth-page ${pageStyles.page}`}><div className={`auth-card ${pageStyles.cardSm}`}>{header}<div className="alert alert-danger py-2 mb-3" role="alert">{t("auth.password_reset.error_missing_token")}</div><button type="button" className="btn btn-primary w-100" onClick={() => navigate("/login")}>{t("auth.password_reset.back_to_login")}</button></div></div></PublicShell>;

  return (
    <PublicShell>
    <div className={`auth-page ${pageStyles.page}`}>
      <div className={`auth-card ${pageStyles.cardSm}`}>
        {header}
        <p className="text-secondary small mb-3">{t("auth.password_reset.confirm_description")}</p>
        <form onSubmit={handleSubmit}>
          <div className="mb-3"><label className="form-label text-secondary small">{t("auth.password_reset.new_password_label")}</label><input type="password" className="form-control auth-input" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required minLength={8} autoComplete="new-password" /></div>
          <div className="mb-3"><label className="form-label text-secondary small">{t("auth.password_reset.confirm_password_label")}</label><input type="password" className="form-control auth-input" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required minLength={8} autoComplete="new-password" /></div>
          {error && <div className="alert alert-danger py-2 mb-3" role="alert">{error}</div>}
          <button type="submit" className="btn btn-primary w-100 mb-3" disabled={loading}>{loading ? t("auth.password_reset.resetting") : t("auth.password_reset.reset_button")}</button>
        </form>
        <p className="text-center text-secondary small mb-0"><a href="/login" className="auth-link" onClick={(e) => { e.preventDefault(); navigate("/login"); }}>{t("auth.password_reset.back_to_login")}</a></p>
      </div>
    </div>
    </PublicShell>
  );
}
