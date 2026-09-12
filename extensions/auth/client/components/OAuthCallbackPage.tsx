/**
 * OAuth callback page — shown at /oauth/callback.
 *
 * The server redirects here after a successful Google OAuth flow with a
 * short-lived one-time ``code`` query parameter.  This page exchanges
 * that code (via POST) for access/refresh tokens, saves them, and
 * redirects to the app root.  Real tokens never appear in the URL.
 *
 * When ``?new=1`` is present (new account created via OAuth), the page
 * redirects to ``/tos-agreement`` instead of ``/`` so the user can
 * complete the mandatory ToS agreement before accessing the app.
 *
 * On failure (missing/expired code), redirects to /login?error=oauth_failed.
 */

import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { exchangeOAuthCode } from "../api";

const ACCESS_TOKEN_KEY = "airunner_access_token";
const REFRESH_TOKEN_KEY = "airunner_refresh_token";

export default function OAuthCallbackPage() {
  const navigate = useNavigate();
  // The ?code= is a one-time handoff token — StrictMode's dev-only double
  // effect invocation would otherwise exchange it twice, minting two
  // separate token pairs and racing which one lands in localStorage.
  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    const params = new URLSearchParams(window.location.search);

    const isNewAccount = params.get("new") === "1";

    // Steam / direct-token flow — tokens are already in the URL.
    const accessToken = params.get("access_token");
    const refreshToken = params.get("refresh_token");
    if (accessToken && refreshToken) {
      localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
      localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
      // Full reload so the AuthProvider picks up the new tokens.
      // New accounts go to ToS agreement; existing accounts go straight in.
      window.location.href = isNewAccount ? "/tos-agreement" : "/";
      return;
    }

    // Google OAuth code-exchange flow.
    const code = params.get("code");

    if (!code) {
      navigate("/login?error=oauth_failed");
      return;
    }

    exchangeOAuthCode(code)
      .then(({ access_token, refresh_token }) => {
        localStorage.setItem(ACCESS_TOKEN_KEY, access_token);
        localStorage.setItem(REFRESH_TOKEN_KEY, refresh_token);
        // Full reload so the AuthProvider picks up the new tokens.
        // New accounts go to ToS agreement; existing accounts go straight in.
        window.location.href = isNewAccount ? "/tos-agreement" : "/";
      })
      .catch(() => {
        navigate("/login?error=oauth_failed");
      });
  }, [navigate]);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        background: "var(--theme-bg, #16162a)",
        color: "var(--theme-text-secondary, #a0a0a8)",
      }}
    >
      Signing in…
    </div>
  );
}
