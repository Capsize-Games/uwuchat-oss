/**
 * UwUchat forgot-password page.
 *
 * Collects an email address and sends a password-reset link.
 * Always shows the same success message regardless of whether the
 * email is registered — prevents user enumeration.
 */

import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PublicShell } from "../layout/PublicShell";
import { UwuLogo } from "./UwuLogo";
import pageStyles from "./AuthShared.module.css";

const RESET_REQUEST_URL = "/api/v1/auth/password-reset/request";

export default function ForgotPasswordPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(RESET_REQUEST_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(
          (body as { detail?: string }).detail
          || t("auth.password_reset.request_error"),
        );
      }
      setSent(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t("auth.password_reset.request_error"),
      );
    } finally {
      setLoading(false);
    }
  };

  if (sent) {
    return (
      <PublicShell>
      <div className={`auth-page ${pageStyles.page}`}>
        <div className={`auth-card ${pageStyles.cardSm}`}>
          <h1 className="auth-title">
            {t("auth.password_reset.request_title")}
          </h1>
          <p className="text-secondary mb-3">
            {t("auth.password_reset.sent_message")}
          </p>
          <button
            type="button"
            className="btn btn-primary w-100"
            onClick={() => navigate("/login")}
          >
            {t("auth.password_reset.back_to_login")}
          </button>
        </div>
      </div>
      </PublicShell>
    );
  }

  return (
    <PublicShell>
    <div className={`auth-page ${pageStyles.page}`}>
      <div className={`auth-card ${pageStyles.cardSm}`}>
        <h1 className="auth-title">
          {t("auth.password_reset.request_title")}
        </h1>
        <p className="text-secondary small mb-3">
          {t("auth.password_reset.request_description")}
        </p>

        <form onSubmit={handleSubmit}>
          <div className="mb-3">
            <label className="form-label text-secondary small">
              {t("auth.password_reset.email_label")}
            </label>
            <input
              type="email"
              className="form-control auth-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </div>

          {error && (
            <div className="alert alert-danger py-2 mb-3" role="alert">
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary w-100 mb-3"
            disabled={loading}
          >
            {loading
              ? t("auth.password_reset.sending")
              : t("auth.password_reset.send_link")}
          </button>
        </form>

        <p className="text-center text-secondary small mb-0">
          <a
            href="/login"
            className="auth-link"
            onClick={(e) => { e.preventDefault(); navigate("/login"); }}
          >
            {t("auth.password_reset.back_to_login")}
          </a>
        </p>
      </div>
    </div>
    </PublicShell>
  );
}
