/**
 * API client helpers for the auth extension.
 *
 * These are used from the browser via the Vite proxy to the server.
 * Token storage and refresh are managed by the Provider component.
 */

const API_BASE = ""; // Uses Vite proxy to /api/v1
const AUTH_PREFIX = "/api/v1/auth";

export interface AgreementFlags {
  tos_agreed?: boolean;
  age_confirmed?: boolean;
  entertainment_confirmed?: boolean;
  sensitive_data_consent_agreed?: boolean;
}

export async function register(
  email: string,
  password: string,
  flags?: AgreementFlags,
  inviteCode?: string,
  waitlistToken?: string,
): Promise<{
  access_token: string;
  refresh_token: string;
  tenant_key: string;
}> {
  const res = await fetch(`${AUTH_PREFIX}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password,
      ...flags,
      invite_code: inviteCode ?? "",
      waitlist_token: waitlistToken ?? "",
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const message =
      typeof err.detail === "string"
        ? err.detail
        : err.detail?.message
        || "Registration failed";
    throw new Error(message);
  }
  return res.json();
}

export async function agreeToTerms(
  flags: Required<AgreementFlags>,
  accessToken: string,
): Promise<void> {
  const res = await fetch(`${AUTH_PREFIX}/agree-tos`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify(flags),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to record agreement");
  }
}

export async function deleteAccount(
  accessToken: string,
  password: string,
): Promise<void> {
  const res = await fetch(`${AUTH_PREFIX}/me/delete`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to delete account");
  }
}

export async function login(
  email: string,
  password: string,
): Promise<{
  access_token: string;
  refresh_token: string;
  tenant_key: string;
}> {
  const res = await fetch(`${AUTH_PREFIX}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Login failed");
  }
  return res.json();
}

export async function exchangeOAuthCode(code: string): Promise<{
  access_token: string;
  refresh_token: string;
  tenant_key: string;
}> {
  const res = await fetch(`${AUTH_PREFIX}/oauth/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "OAuth exchange failed");
  }
  return res.json();
}

export async function refreshAccessToken(
  refreshToken: string,
): Promise<{ access_token: string }> {
  const res = await fetch(`${AUTH_PREFIX}/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) {
    throw new Error("Token refresh failed");
  }
  return res.json();
}

export async function getMe(accessToken: string): Promise<{
  id: number;
  email: string;
  username: string;
  is_verified: boolean;
  is_superuser: boolean;
}> {
  const res = await fetch(`${AUTH_PREFIX}/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) {
    throw new Error("Failed to fetch user profile");
  }
  return res.json();
}

export async function logout(accessToken: string): Promise<void> {
  // Best-effort: revoke refresh tokens server-side. The client clears
  // local tokens regardless of the outcome.
  try {
    await fetch(`${AUTH_PREFIX}/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
    });
  } catch {
    // ignore — local tokens are still cleared by the caller
  }
}

export async function verifyEmail(
  token: string,
): Promise<{ message: string; already_verified: boolean }> {
  const res = await fetch(
    `${AUTH_PREFIX}/verify?token=${encodeURIComponent(token)}`,
  );
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Verification failed");
  }
  return res.json();
}

export async function resendVerification(
  accessToken: string,
): Promise<{ message: string; sent: boolean }> {
  const res = await fetch(`${AUTH_PREFIX}/send-verification`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to send verification email");
  }
  return res.json();
}
