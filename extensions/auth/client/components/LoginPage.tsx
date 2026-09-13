/**
 * Login page — shown at /login when not authenticated.
 *
 * Supports email/password signin and Google OAuth signin.
 */

import { FormEvent, ReactNode, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../Provider";
import { AuthCard } from "./AuthCard";

const GOOGLE_OAUTH_URL = "/api/v1/auth/oauth/google/login";
const CAPABILITIES_URL = "/api/v1/auth/oauth/capabilities";

interface LoginPageProps {
  bottomSlot?: ReactNode;
}

export default function LoginPage({ bottomSlot }: LoginPageProps) {
  const navigate = useNavigate();
  const { login, isLoggingIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
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

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  };

  const params = new URLSearchParams(window.location.search);
  const oauthError = params.get("error");

  return (
    <AuthCard title="Sign In">
      {oauthError && (
        <div className="alert alert-danger py-2 mb-3" role="alert">
          {oauthError === "invalid_oauth_state" &&
            "Sign-in failed due to a security issue. Please try again."}
          {oauthError === "oauth_failed" &&
            "Could not sign in with Google. Please try again."}
          {oauthError === "google_oauth_not_configured" &&
            "Google sign-in isn't available right now — please use email/password or try again later."}
          {oauthError === "twitch_oauth_not_configured" &&
            "Twitch sign-in isn't available right now — please use email/password or try again later."}
          {oauthError === "email_exists" &&
            (params.get("detail") ||
              "An account with this email already exists. Sign in with your password.")}
          {oauthError !== "invalid_oauth_state" &&
            oauthError !== "oauth_failed" &&
            oauthError !== "google_oauth_not_configured" &&
            oauthError !== "twitch_oauth_not_configured" &&
            oauthError !== "email_exists" &&
            oauthError}
        </div>
      )}

      {params.get("verified") === "1" && (
        <div className="alert alert-success py-2 mb-3" role="alert">
          Email verified successfully. You can now sign in.
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="mb-3">
          <label className="form-label text-secondary small">Email</label>
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
          <label className="form-label text-secondary small">Password</label>
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
          disabled={isLoggingIn}
        >
          {isLoggingIn ? "Signing in…" : "Sign In"}
        </button>
      </form>

      <div className="auth-divider">
        <span>or</span>
      </div>

      {googleConfigured && (
        <button
          type="button"
          className="btn auth-google-btn w-100 mb-3"
          onClick={() => { window.location.href = GOOGLE_OAUTH_URL; }}
          disabled={isLoggingIn}
        >
          <GoogleIcon />
          Sign in with Google
        </button>
      )}

      <p className="text-center text-secondary small mb-0">
        Don't have an account?{" "}
        <a
          href="/register"
          className="auth-link"
          onClick={(e) => { e.preventDefault(); navigate("/register"); }}
        >
          Register
        </a>
      </p>

      {bottomSlot}
    </AuthCard>
  );
}

function GoogleIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 18 18"
      xmlns="http://www.w3.org/2000/svg"
      style={{ marginRight: 8, flexShrink: 0 }}
    >
      <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.874 2.684-6.616z" fill="#4285F4"/>
      <path d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="#34A853"/>
      <path d="M3.964 10.706A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.706V4.962H.957A8.996 8.996 0 0 0 0 9c0 1.49.348 2.903.957 4.138l3.007-2.432z" fill="#FBBC05"/>
      <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.962l3.007 2.332C4.672 5.164 6.656 3.58 9 3.58z" fill="#EA4335"/>
    </svg>
  );
}
