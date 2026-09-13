/**
 * UwUchat login page.
 *
 * Overrides the framework LoginPage to add the UwUchat logo
 * branding above the sign-in form so users know what they're
 * signing into.
 */

import { FormEvent, useEffect, useState } from "react";
import { LogIn } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { PublicShell } from "../layout/PublicShell";
import { UwuLogo } from "./UwuLogo";
import pageStyles from "./AuthShared.module.css";

const GOOGLE_OAUTH_URL = "/api/v1/auth/oauth/google/login";
const STEAM_AUTH_API = "/api/v1/steam/auth/login?mode=auth";
const CAPABILITIES_URL = "/api/v1/auth/oauth/capabilities";
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function LoginPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { login, isLoggingIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [steamLoading, setSteamLoading] = useState(false);
  const [googleConfigured, setGoogleConfigured] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(CAPABILITIES_URL)
      .then((r) => r.json())
      .then((d: { google?: boolean }) => {
        if (!cancelled) setGoogleConfigured(!!d.google);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const canSubmit =
    !isLoggingIn && EMAIL_PATTERN.test(email.trim()) && password.trim() !== "";

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("auth.login.error_default"));
    }
  };

  const params = new URLSearchParams(window.location.search);
  const oauthError = params.get("error");

  return (
    <PublicShell>
    <div className={`auth-page ${pageStyles.page}`}>
      <div className={`auth-card ${pageStyles.cardSm}`}>
        <h1 className="auth-title d-flex align-items-center gap-2">
          <LogIn size={22} />
          {t("auth.login.title")}
        </h1>

        {oauthError && (
          <div className="alert alert-danger py-2 mb-3" role="alert">
            {oauthError === "invalid_oauth_state" &&
              t("auth.login.error_oauth_state")}
            {oauthError === "oauth_failed" &&
              t("auth.login.error_oauth_failed")}
            {oauthError === "google_oauth_not_configured" &&
              t("auth.login.error_google_oauth_not_configured")}
            {oauthError === "twitch_oauth_not_configured" &&
              t("auth.login.error_twitch_oauth_not_configured")}
            {oauthError === "steam_auth_failed" &&
              t("auth.login.error_steam_auth_failed")}
            {oauthError === "email_exists" &&
              (params.get("detail") ||
                t("auth.login.error_email_exists"))}
            {oauthError !== "invalid_oauth_state" &&
              oauthError !== "oauth_failed" &&
              oauthError !== "google_oauth_not_configured" &&
              oauthError !== "twitch_oauth_not_configured" &&
              oauthError !== "steam_auth_failed" &&
              oauthError !== "email_exists" &&
              oauthError}
          </div>
        )}

        {params.get("verified") === "1" && (
          <div className="alert alert-success py-2 mb-3" role="alert">
            {t("auth.login.verified_success")}
          </div>
        )}

        {params.get("reset") === "1" && (
          <div className="alert alert-success py-2 mb-3" role="alert">
            {t("auth.login.reset_success")}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="mb-3">
            <label className="form-label text-secondary small">{t("auth.login.email_label")}</label>
            <input
              type="email"
              name="email"
              className="form-control auth-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </div>
          <div className="mb-3">
            <label className="form-label text-secondary small">{t("auth.login.password_label")}</label>
            <input
              type="password"
              name="password"
              className="form-control auth-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
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
            disabled={!canSubmit}
          >
            {isLoggingIn ? t("auth.login.submitting") : t("auth.login.submit")}
          </button>
        </form>

        <p className="text-center text-secondary small mb-0">
          <a
            href="/forgot-password"
            className="auth-link"
            onClick={(e) => { e.preventDefault(); navigate("/forgot-password"); }}
          >
            {t("auth.login.forgot_password")}
          </a>
        </p>

        <div className="auth-divider">
          <span>{t("auth.login.divider_or")}</span>
        </div>

        {googleConfigured && (
          <button
            type="button"
            className="btn auth-provider-btn w-100 mb-3"
            onClick={() => { window.location.href = GOOGLE_OAUTH_URL; }}
            disabled={isLoggingIn}
          >
            <span className="auth-provider-btn-content">
              <GoogleIcon />
              <span className="auth-provider-btn-label">{t("auth.login.google")}</span>
            </span>
          </button>
        )}

        <button
          type="button"
          className="btn auth-provider-btn w-100 mb-3"
          onClick={async () => {
            setSteamLoading(true);
            try {
              const res = await fetch(STEAM_AUTH_API);
              if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(
                  (err as { detail?: string }).detail || "Steam sign-in failed",
                );
              }
              const data = await res.json() as { url: string };
              window.location.href = data.url;
            } catch (err) {
              console.error("Steam sign-in failed:", err);
              setSteamLoading(false);
            }
          }}
          disabled={isLoggingIn || steamLoading}
        >
          <span className="auth-provider-btn-content">
            <SteamIcon />
            <span className="auth-provider-btn-label">
              {steamLoading ? t("auth.login.steam_connecting") : t("auth.login.steam")}
            </span>
          </span>
        </button>

        <p className="text-center text-secondary small mb-0">
          {t("auth.login.no_account")}{" "}
          <a
            href="/register"
            className="auth-link"
            onClick={(e) => { e.preventDefault(); navigate("/register"); }}
          >
            {t("auth.login.register_link")}
          </a>
        </p>
      </div>
    </div>
    </PublicShell>
  );
}

function SteamIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      xmlns="http://www.w3.org/2000/svg"
      fill="currentColor"
    >
      <path d="M11.979 0C5.678 0 .511 4.86.022 11.037l6.432 2.658c.545-.371 1.203-.59 1.912-.59.063 0 .125.004.188.006l2.861-4.142V8.91c0-2.495 2.028-4.524 4.524-4.524 2.494 0 4.524 2.031 4.524 4.527s-2.03 4.525-4.524 4.525h-.105l-4.076 2.911c0 .052.004.105.004.159 0 1.875-1.515 3.396-3.39 3.396-1.635 0-3.016-1.173-3.331-2.727L.436 15.27C1.862 20.307 6.486 24 11.979 24c6.627 0 11.999-5.373 11.999-12S18.605 0 11.979 0zM7.54 18.21l-1.473-.61c.262.543.714.999 1.314 1.25 1.297.539 2.793-.076 3.332-1.375.263-.63.264-1.319.005-1.949s-.75-1.121-1.377-1.383c-.624-.26-1.29-.249-1.878-.03l1.523.63c.956.4 1.409 1.5 1.009 2.455-.397.957-1.497 1.41-2.454 1.012H7.54zm11.415-9.303c0-1.662-1.353-3.015-3.015-3.015-1.665 0-3.015 1.353-3.015 3.015 0 1.665 1.35 3.015 3.015 3.015 1.663 0 3.015-1.35 3.015-3.015zm-5.273-.005c0-1.252 1.013-2.266 2.265-2.266 1.249 0 2.266 1.014 2.266 2.266 0 1.251-1.017 2.265-2.266 2.265-1.253 0-2.265-1.014-2.265-2.265z"/>
    </svg>
  );
}

function GoogleIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      xmlns="http://www.w3.org/2000/svg"
      fill="currentColor"
    >
      <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/>
    </svg>
  );
}

function BlueskyIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      xmlns="http://www.w3.org/2000/svg"
      fill="currentColor"
    >
      <path d="M5.202 2.857C7.954 4.922 10.913 9.11 12 11.358c1.087-2.247 4.046-6.436 6.798-8.501C20.783 1.366 24 .213 24 3.883c0 .732-.42 6.156-.667 7.037-.856 3.061-3.978 3.842-6.755 3.37 4.854.826 6.089 3.562 3.422 6.299-5.065 5.196-7.28-1.304-7.847-2.97-.104-.305-.152-.448-.153-.327 0-.121-.05.022-.153.327-.568 1.666-2.782 8.166-7.847 2.97-2.667-2.737-1.432-5.473 3.422-6.3-2.777.473-5.899-.308-6.755-3.369C.42 10.04 0 4.615 0 3.883c0-3.67 3.217-2.517 5.202-1.026"/>
    </svg>
  );
}
