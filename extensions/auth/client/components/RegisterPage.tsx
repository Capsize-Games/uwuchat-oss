/**
 * Registration page — shown at /register.
 *
 * Supports email/password signup and Google OAuth signup.
 * Supports waitlist-gated registrations: when the server returns
 * signup_mode: "waitlist" and no waitlist_token is in the URL, an
 * email-only "Join the waitlist" form is shown instead of the
 * password/registration form.
 *
 * `bottomSlot` is an extension point for project-specific content (e.g.
 * UwUchat's three ToS agreement checkboxes).
 */

import { useEffect, useState, ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../Provider";
import { useSignupMode } from "../hooks/useSignupMode";
import { AuthCard } from "./AuthCard";
import type { AgreementFlags } from "../api";

const GOOGLE_OAUTH_URL = "/api/v1/auth/oauth/google/login";
const CAPABILITIES_URL = "/api/v1/auth/oauth/capabilities";
const WAITLIST_JOIN_URL = "/api/v1/auth/waitlist/join";

interface RegisterPageProps {
  /** Rendered below the password fields, inside the form, before the submit button. */
  bottomSlot?: ReactNode;
  /** If provided, these flags are passed to the register API call. */
  agreementFlags?: AgreementFlags;
  /** When true, the submit button is disabled regardless of form state. */
  agreementsRequired?: boolean;
  /** Set to true when all project-required checkboxes are checked. */
  agreementsComplete?: boolean;
}

export default function RegisterPage({
  bottomSlot,
  agreementFlags,
  agreementsRequired = false,
  agreementsComplete = true,
}: RegisterPageProps) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { register, isLoggingIn } = useAuth();
  const { signup_mode, loading: modeLoading } = useSignupMode();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isRegistered, setIsRegistered] = useState(false);
  const [googleConfigured, setGoogleConfigured] = useState(false);
  const [joinedWaitlist, setJoinedWaitlist] = useState(false);
  const [joiningWaitlist, setJoiningWaitlist] = useState(false);

  // Extract waitlist token from URL if present
  const waitlistToken = searchParams.get("waitlist_token") ?? "";

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
    !isLoggingIn && (!agreementsRequired || agreementsComplete);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (username.trim().length < 3) {
      setError("Username must be at least 3 characters");
      return;
    }

    try {
      await register(
        email, username, password, agreementFlags,
        waitlistToken || undefined,
      );
      setIsRegistered(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    }
  };

  const handleJoinWaitlist = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setJoiningWaitlist(true);
    try {
      const res = await fetch(WAITLIST_JOIN_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(
          typeof err.detail === "string"
            ? err.detail
            : err.detail?.message || "Failed to join waitlist",
        );
      }
      setJoinedWaitlist(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to join waitlist");
    } finally {
      setJoiningWaitlist(false);
    }
  };

  // Show waitlist confirmation after successful join.
  if (joinedWaitlist) {
    return (
      <AuthCard title="You're on the list!">
        <p className="text-secondary text-center mb-4">
          We'll send an invitation to{" "}
          <strong className="text-light">{email}</strong> when a spot
          opens up.
        </p>
        <button
          className="btn btn-primary w-100"
          onClick={() => navigate("/")}
        >
          Back to Home
        </button>
      </AuthCard>
    );
  }

  // Show waitlist join form when waitlist mode is active and no token
  // is present (and we're not still loading the mode).
  if (
    !modeLoading
    && signup_mode === "waitlist"
    && !waitlistToken
    && !isRegistered
  ) {
    return (
      <AuthCard title="Join the waitlist">
        <p className="text-secondary text-center mb-4">
          Registration is currently invite-only. Enter your email to
          join the waitlist and we'll let you know when a spot opens
          up.
        </p>
        <form onSubmit={handleJoinWaitlist}>
          <div className="mb-3">
            <label className="form-label text-secondary small">
              Email
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
            disabled={joiningWaitlist || !email.trim()}
          >
            {joiningWaitlist ? "Joining…" : "Join Waitlist"}
          </button>
        </form>

        <p className="text-center text-secondary small mb-0">
          Already have an invite?{" "}
          <a
            href="/login"
            className="auth-link"
            onClick={(e) => { e.preventDefault(); navigate("/login"); }}
          >
            Sign in
          </a>
        </p>
      </AuthCard>
    );
  }

  if (isRegistered) {
    return (
      <AuthCard title="Check your email">
        <p className="text-secondary text-center mb-4">
          We sent a verification link to{" "}
          <strong className="text-light">{email}</strong>. Click the link in
          that email to activate your account.
        </p>
        <p className="text-secondary text-center small mb-4">
          You are signed in and can use the app while waiting for verification.
        </p>
        <button className="btn btn-primary w-100" onClick={() => navigate("/")}>
          Continue to App
        </button>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Create Account">
      <form onSubmit={handleSubmit}>
        <div className="mb-3">
          <label className="form-label text-secondary small">Email</label>
          <input
            type="email"
            className="form-control auth-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
        </div>
        <div className="mb-3">
          <label className="form-label text-secondary small">Username</label>
          <input
            type="text"
            className="form-control auth-input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            minLength={3}
            autoComplete="username"
          />
        </div>
        <div className="mb-3">
          <label className="form-label text-secondary small">Password</label>
          <input
            type="password"
            className="form-control auth-input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
        </div>
        <div className="mb-3">
          <label className="form-label text-secondary small">
            Confirm Password
          </label>
          <input
            type="password"
            className="form-control auth-input"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
        </div>

        {bottomSlot}

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
          {isLoggingIn ? "Creating account…" : "Create Account"}
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
          Sign up with Google
        </button>
      )}

      <p className="text-center text-secondary small mb-0">
        Already have an account?{" "}
        <a
          href="/login"
          className="auth-link"
          onClick={(e) => { e.preventDefault(); navigate("/login"); }}
        >
          Sign in
        </a>
      </p>
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
